package launch

import (
	"bytes"
	"context"
	"errors"
	"net/http"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

// Break caught: accepting uppercase input but keeping its raw identity in state.
func TestConfigureCanonicalTeacherIdentity(t *testing.T) {
	c, _ := controllerFixture(t)
	// Use a fresh Store, not the already configured fixture.
	c.store = &Store{Root: t.TempDir()}
	in := setupFixture()
	in.TeacherUsername = "Teacher_One"
	if e := c.Configure(in); e != nil {
		t.Fatal(e)
	}
	_, st, e := c.store.Load()
	if e != nil || st.TeacherUsername != "teacher_one" {
		t.Fatalf("teacher identity was not canonical: %v", e)
	}
}

// Break caught: an otherwise successful new bootstrap returns lowercase username.
func TestMixedCaseNewInstallReachesReady(t *testing.T) {
	c, _ := controllerFixture(t)
	c.store = &Store{Root: t.TempDir()}
	in := setupFixture()
	in.TeacherUsername = "Teacher_One"
	if e := c.Configure(in); e != nil {
		t.Fatal(e)
	}
	if e := c.Start(context.Background(), &in); e != nil {
		t.Fatal(e)
	}
	_, st, e := c.store.Load()
	if e != nil || st.Phase != READY || st.TeacherUsername != "teacher_one" || st.TeacherID != "fixture-teacher-id" {
		t.Fatal("new install did not reach READY with canonical identity")
	}
}

// Break caught: the old migrated checkpoint requires case-sensitive resume input.
func TestLegacyMixedCaseMigratedResumePreservesConfig(t *testing.T) {
	for _, entered := range []string{"Teacher_One", "teacher_one", "TEACHER_ONE"} {
		t.Run(entered, func(t *testing.T) {
			c, r := controllerFixture(t)
			cfg, st, _ := c.store.Load()
			st.TeacherUsername = "Teacher_One"
			st.Phase = ERROR
			st.Checkpoint = "migrated"
			if e := c.store.SaveState(st); e != nil {
				t.Fatal(e)
			}
			before, e := os.ReadFile(filepath.Join(c.store.Root, ".env"))
			if e != nil {
				t.Fatal(e)
			}
			in := setupFixture()
			in.TeacherUsername = entered
			if e := c.Start(context.Background(), &in); e != nil {
				t.Fatal(e)
			}
			after, _ := os.ReadFile(filepath.Join(c.store.Root, ".env"))
			gotCfg, got, e := c.store.Load()
			if e != nil || got.Phase != READY || got.TeacherUsername != "teacher_one" || got.TeacherID != "fixture-teacher-id" || got.InstallID != st.InstallID || !bytes.Equal(before, after) || gotCfg.Neo4jPassword != cfg.Neo4jPassword {
				t.Fatal("resume changed identity/config or did not complete")
			}
			for _, q := range r.Requests {
				if strings.HasSuffix(strings.Join(q.Args, " "), " migrate") {
					t.Fatal("migrated checkpoint reran migration")
				}
			}
		})
	}
}

func TestLegacyMixedCaseRejectsDifferentTeacher(t *testing.T) {
	c, _ := controllerFixture(t)
	_, st, _ := c.store.Load()
	st.TeacherUsername = "Teacher_One"
	st.Phase = ERROR
	st.Checkpoint = "migrated"
	c.store.SaveState(st)
	in := setupFixture()
	in.TeacherUsername = "teacher_two"
	e := c.Start(context.Background(), &in)
	var f *Failure
	if !errors.As(e, &f) || f.Code != "FIELD" {
		t.Fatal("different teacher accepted")
	}
}

func TestBootstrapCanonicalComparisonStillRejectsForeignIdentity(t *testing.T) {
	for _, name := range []string{"teacher_one", "teacher_two"} {
		r := &recordingRunner{Response: ProcessResult{Stdout: []byte(`{"user_id":"fixture-id","username":"` + name + `","created":false}`)}}
		_, e := dockerFixture(r).Bootstrap(context.Background(), InstallState{InstallID: "0123456789abcdef", TeacherUsername: "Teacher_One"}, []byte(`{}`))
		if (name == "teacher_one") != (e == nil) {
			t.Fatal("bootstrap identity comparison incorrect")
		}
	}
}

// Break caught: finding Docker by absolute path while its subprocess helper stays absent.
func TestDockerRunsHelperFromLocatedToolDirectory(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("Unix subprocess behavior; cross-compile Windows separately")
	}
	dir := filepath.Join(t.TempDir(), "Docker tools with spaces")
	if e := os.Mkdir(dir, 0700); e != nil {
		t.Fatal(e)
	}
	cli := filepath.Join(dir, "docker")
	if e := os.WriteFile(cli, []byte("#!/bin/sh\nexec docker-credential-fixture\n"), 0700); e != nil {
		t.Fatal(e)
	}
	if e := os.WriteFile(filepath.Join(dir, "docker-credential-fixture"), []byte("#!/bin/sh\nprintf 'helper-ready'\n"), 0700); e != nil {
		t.Fatal(e)
	}
	t.Setenv("PATH", "/usr/bin:/bin")
	t.Setenv("NEO4J_PASSWORD", "fixture-inherited-secret")
	d := dockerFixture(nil)
	d.CLI = cli
	result, e := d.run(context.Background(), []string{"info"}, nil)
	if e != nil || string(result.Stdout) != "helper-ready" {
		t.Fatalf("helper was not discoverable: %v", e)
	}
	r := &recordingRunner{}
	d.Runner = r
	d.run(context.Background(), []string{"info"}, nil)
	paths := []string{}
	for _, v := range r.Requests[0].Env {
		if strings.HasPrefix(v, "PATH=") {
			paths = append(paths, strings.TrimPrefix(v, "PATH="))
		}
		if strings.HasPrefix(v, "NEO4J_PASSWORD=") {
			t.Fatal("inherited secrets leaked")
		}
	}
	if len(paths) != 1 || !strings.HasSuffix(paths[0], "/usr/bin:/bin") {
		t.Fatal("original PATH lost or duplicate env key")
	}
	t.Setenv("PATH", dir+string(os.PathListSeparator)+"/usr/bin:/bin")
	r.Requests = nil
	d.run(context.Background(), []string{"info"}, nil)
	for _, v := range r.Requests[0].Env {
		if strings.HasPrefix(v, "PATH=") {
			count := 0
			for _, p := range filepath.SplitList(strings.TrimPrefix(v, "PATH=")) {
				if p == dir {
					count++
				}
			}
			if count != 1 {
				t.Fatal("tool dir duplicated")
			}
		}
	}
}

// Real synthetic Docker account: old uppercase migrated state resumes without resetting the password.
func TestLocalLegacyMixedCaseResumePreservesFirstPassword(t *testing.T) {
	c, ctx := smokeController(t)
	before, st, e := c.store.Load()
	if e != nil {
		t.Fatal(e)
	}
	firstID := st.TeacherID
	installID := st.InstallID
	if e = c.Stop(ctx); e != nil {
		t.Fatal(e)
	}
	st.Fresh = true
	st.TeacherID = ""
	st.TeacherUsername = "Teacher_One"
	st.Checkpoint = "migrated"
	st.Phase = ERROR
	if e = c.store.SaveState(st); e != nil {
		t.Fatal(e)
	}
	in := setupFixture()
	in.WebPort = st.WebPort
	in.TeacherUsername = "TEACHER_ONE"
	in.TeacherPassword = NewSecret("different-fixture-password")
	in.ConfirmPassword = in.TeacherPassword
	if e = c.Start(ctx, &in); e != nil {
		t.Fatal(e)
	}
	after, got, e := c.store.Load()
	if e != nil || got.Phase != READY || got.TeacherUsername != "teacher_one" || got.TeacherID != firstID || got.InstallID != installID || before.ModelCredentialKey != after.ModelCredentialKey || before.Neo4jPassword != after.Neo4jPassword {
		t.Fatal("legacy identity/config not preserved")
	}
	response := postSynthetic(t, ctx, webURL(got.WebPort)+"/api/v1/auth/login", map[string]string{"username": "teacher_one", "password": "fixture-pass-one"})
	if response["user"].(map[string]any)["id"] != firstID {
		t.Fatal("original account changed")
	}
	reqBody := strings.NewReader(`{"username":"teacher_one","password":"different-fixture-password"}`)
	req, e := http.NewRequestWithContext(ctx, "POST", webURL(got.WebPort)+"/api/v1/auth/login", reqBody)
	if e != nil {
		t.Fatal(e)
	}
	req.Header.Set("Content-Type", "application/json")
	r, e := http.DefaultClient.Do(req)
	if e != nil {
		t.Fatal(e)
	}
	defer r.Body.Close()
	if r.StatusCode != http.StatusUnauthorized {
		t.Fatalf("replacement password unexpectedly accepted: %d", r.StatusCode)
	}
}

func TestLegacyMixedCaseAppFailureKeepsTeacherCheckpoint(t *testing.T) {
	c, r := controllerFixture(t)
	_, st, _ := c.store.Load()
	st.TeacherUsername = "Teacher_One"
	st.Phase = ERROR
	st.Checkpoint = "migrated"
	if e := c.store.SaveState(st); e != nil {
		t.Fatal(e)
	}
	r.FailApp = true
	in := setupFixture()
	in.TeacherUsername = "Teacher_One"
	if e := c.Start(context.Background(), &in); e == nil {
		t.Fatal("app failure ignored")
	}
	_, got, e := c.store.Load()
	if e != nil || got.TeacherID != "fixture-teacher-id" || got.Checkpoint != "teacher" || got.TeacherUsername != "teacher_one" || got.Phase != ERROR {
		t.Fatal("teacher checkpoint lost after downstream error")
	}
	r.FailApp = false
	r.Requests = nil
	if e = c.Start(context.Background(), nil); e != nil {
		t.Fatal(e)
	}
	for _, q := range r.Requests {
		if strings.HasSuffix(strings.Join(q.Args, " "), " bootstrap") {
			t.Fatal("existing teacher bootstrap reran")
		}
	}
}

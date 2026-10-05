package launch

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

// Explicit test-only image adapter: production pinned-pull path is NOT claimed tested here.
type localImageRunner struct {
	base   Runner
	images map[string]string
}

func (r localImageRunner) Run(ctx context.Context, q ProcessRequest) (ProcessResult, error) {
	q.Env = append([]string{}, q.Env...)
	q.Args = append([]string{}, q.Args...)
	if len(q.Args) > 0 && q.Args[len(q.Args)-1] == "pull" {
		return ProcessResult{}, nil
	}
	for i, s := range q.Env {
		for k, image := range r.images {
			if strings.HasPrefix(s, k+"=") {
				q.Env[i] = k + "=" + image
			}
		}
	}
	for i, s := range q.Args {
		for k, prefix := range map[string]string{"BACKEND_IMAGE": "ghcr.io/arvinhanye/smartsketch-backend@sha256:", "FRONTEND_IMAGE": "ghcr.io/arvinhanye/smartsketch-frontend@sha256:", "NEO4J_IMAGE": "neo4j@sha256:"} {
			if strings.HasPrefix(s, prefix) {
				q.Args[i] = r.images[k]
			}
		}
	}
	return r.base.Run(ctx, q)
}
func smokeController(t *testing.T) (*Controller, context.Context) {
	t.Helper()
	if os.Getenv("SMARTSKETCH_STARTUP_SMOKE") != "1" {
		t.Skip("explicit isolated Docker smoke only; not release acceptance")
	}
	cli, e := FindDocker()
	if e != nil {
		t.Fatal(e)
	}
	images := map[string]string{"BACKEND_IMAGE": os.Getenv("STARTUP_TEST_BACKEND"), "FRONTEND_IMAGE": os.Getenv("STARTUP_TEST_FRONTEND"), "NEO4J_IMAGE": "neo4j:5.26-community"}
	for _, key := range []string{"BACKEND_IMAGE", "FRONTEND_IMAGE"} {
		if !strings.HasPrefix(images[key], "smartsketch-startup-test-") {
			t.Fatal("only owned synthetic test image tags accepted")
		}
	}
	repo, e := filepath.Abs("../../..")
	if e != nil {
		t.Fatal(e)
	}
	compose := filepath.Join(repo, "packaging", "compose.release.yaml")
	b, e := os.ReadFile(compose)
	if e != nil {
		t.Fatal(e)
	}
	sum := sha256.Sum256(b)
	m := manifestFixture()
	m.ComposeSHA256 = hex.EncodeToString(sum[:])
	root := t.TempDir()
	bundle := t.TempDir()
	mb, _ := json.Marshal(m)
	mp := filepath.Join(bundle, "release-manifest.json")
	os.WriteFile(mp, mb, 0600)
	store := &Store{Root: root}
	if e = store.SeedRelease(mp, compose, m); e != nil {
		t.Fatal(e)
	}
	runner := localImageRunner{ExecRunner{}, images}
	d := &Docker{CLI: cli, ComposePath: compose, EnvPath: filepath.Join(root, ".env"), Manifest: m, Runner: runner}
	c := NewController(store, d, nil)
	in := setupFixture()
	l, e := net.Listen("tcp4", "127.0.0.1:0")
	if e != nil {
		t.Fatal(e)
	}
	in.WebPort = l.Addr().(*net.TCPAddr).Port
	l.Close()
	if e = c.Configure(in); e != nil {
		t.Fatal(e)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Minute)
	t.Cleanup(cancel)
	t.Cleanup(func() {
		_, st, e := store.Load()
		if e != nil {
			return
		}
		cleanupCtx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
		defer cancel()
		if _, e = d.Inspect(cleanupCtx, st); e != nil {
			t.Errorf("cleanup ownership failed; retained test resources")
			return
		}
		_ = d.Stop(cleanupCtx, st)
		p, _ := project(st)
		r, e := d.run(cleanupCtx, []string{"container", "ls", "--all", "--filter", "label=io.smartsketch.installation=" + st.InstallID, "--format", "{{.ID}}"}, nil)
		if e == nil {
			for _, id := range strings.Fields(string(r.Stdout)) {
				_, _ = d.run(cleanupCtx, []string{"container", "rm", id}, nil)
			}
		}
		r, e = d.run(cleanupCtx, []string{"volume", "ls", "--filter", "name=^" + p + "_", "--format", "{{.Name}}"}, nil)
		if e == nil {
			for _, name := range strings.Fields(string(r.Stdout)) {
				result, e := d.run(cleanupCtx, []string{"volume", "inspect", name, "--format", "{{json .Labels}}"}, nil)
				var labels map[string]string
				if e == nil && json.Unmarshal(result.Stdout, &labels) == nil && checkVolumeOwner(labels, st.InstallID) == nil {
					_, _ = d.run(cleanupCtx, []string{"volume", "rm", name}, nil)
				}
			}
		}
	})
	if e = c.Start(ctx, &in); e != nil {
		v, _ := c.Status(ctx)
		t.Fatalf("synthetic startup failed stage=%s code=%v", v.Stage, e)
	}
	return c, ctx
}
func postSynthetic(t *testing.T, ctx context.Context, url string, data map[string]string) map[string]any {
	t.Helper()
	b, _ := json.Marshal(data)
	req, _ := http.NewRequestWithContext(ctx, "POST", url, bytes.NewReader(b))
	req.Header.Set("Content-Type", "application/json")
	r, e := http.DefaultClient.Do(req)
	if e != nil {
		t.Fatal("loopback request failed")
	}
	defer r.Body.Close()
	body, _ := io.ReadAll(io.LimitReader(r.Body, 16384))
	if r.StatusCode < 200 || r.StatusCode >= 300 {
		t.Fatalf("loopback request status=%d", r.StatusCode)
	}
	var out map[string]any
	if json.Unmarshal(body, &out) != nil {
		t.Fatal("response invalid")
	}
	return out
}
func TestLocalReleaseLoginStopRestart(t *testing.T) {
	c, ctx := smokeController(t)
	cfg, st, _ := c.store.Load()
	url := webURL(st.WebPort)
	teacher := postSynthetic(t, ctx, url+"/api/v1/auth/login", map[string]string{"username": "teacher_one", "password": "fixture-pass-one"})
	if teacher["user"].(map[string]any)["role"] != "teacher" {
		t.Fatal("teacher role")
	}
	student := postSynthetic(t, ctx, url+"/api/v1/auth/register", map[string]string{"username": "fixture_student", "password": "fixture-pass-one"})
	id := student["user"].(map[string]any)["id"]
	if e := c.Stop(ctx); e != nil {
		t.Fatal(e)
	}
	if e := c.Start(ctx, nil); e != nil {
		t.Fatal(e)
	}
	after, got, _ := c.store.Load()
	if after.ModelCredentialKey.value != cfg.ModelCredentialKey.value || st.InstallID != got.InstallID {
		t.Fatal("rekeyed")
	}
	logged := postSynthetic(t, ctx, url+"/api/v1/auth/login", map[string]string{"username": "fixture_student", "password": "fixture-pass-one"})
	if logged["user"].(map[string]any)["id"] != id {
		t.Fatal("lost account")
	}
}
func TestLocalOwnedBackupRestore(t *testing.T) {
	c, ctx := smokeController(t)
	target := manifestFixture()
	target.Version = "fixture-2"
	set, e := c.PrepareUpgrade(ctx, target, true)
	if e != nil {
		t.Fatal(e)
	}
	if e = c.Restore(ctx, set, true); e == nil {
		t.Fatal("restore did not require second confirmation")
	} else if f, ok := e.(*Failure); !ok || f.Stage != "restore-confirm" {
		t.Fatalf("restore stage %v", e)
	}
	if e = c.Restore(ctx, set, true); e != nil {
		t.Fatal(e)
	}
	_, st, _ := c.store.Load()
	if st.DataGeneration == "" {
		t.Fatal("staging mapping not activated")
	}
	postSynthetic(t, ctx, webURL(st.WebPort)+"/api/v1/auth/login", map[string]string{"username": "teacher_one", "password": "fixture-pass-one"})
	original, _ := volumeNames(st, "")
	result, e := c.docker.run(ctx, []string{"volume", "inspect", original["app"], "--format", "{{json .Labels}}"}, nil)
	if e != nil || !strings.Contains(string(result.Stdout), st.InstallID) {
		t.Fatal("original volume lost")
	}
}
func TestLocalTwoInstallationsRemainIndependent(t *testing.T) {
	a, ctx := smokeController(t)
	b, _ := smokeController(t)
	_, sa, _ := a.store.Load()
	_, sb, _ := b.store.Load()
	if sa.InstallID == sb.InstallID || sa.WebPort == sb.WebPort {
		t.Fatal("installation collision")
	}
	postSynthetic(t, ctx, webURL(sa.WebPort)+"/api/v1/auth/register", map[string]string{"username": "only_first", "password": "fixture-pass-one"})
	if e := a.Stop(ctx); e != nil {
		t.Fatal(e)
	}
	v, e := b.Status(ctx)
	if e != nil || v.Phase != READY {
		t.Fatal("stopping first changed second")
	}
	_ = fmt.Sprint(v)
}

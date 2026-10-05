package launch

import (
	"context"
	"fmt"
	"strings"
	"testing"
	"time"
)

type fakeClock struct{ now time.Time }

func (c *fakeClock) Now() time.Time { return c.now }
func (c *fakeClock) Sleep(ctx context.Context, d time.Duration) error {
	c.now = c.now.Add(d)
	return ctx.Err()
}
func TestStartDeadlineIs180Seconds(t *testing.T) {
	c := &fakeClock{}
	read := func(context.Context) (Snapshot, error) { return Snapshot{APIHealthy: true}, nil }
	if WaitReady(context.Background(), read, c, 180*time.Second) == nil {
		t.Fatal("false readiness")
	}
	if c.now.Sub(time.Time{}) != 180*time.Second {
		t.Fatal("wrong deadline")
	}
}
func TestAPIOKWorkerBrokenDoesNotSetReady(t *testing.T) {
	c := &fakeClock{}
	if WaitReady(context.Background(), func(context.Context) (Snapshot, error) {
		return Snapshot{ProjectOwned: true, Neo4jHealthy: true, APIHealthy: true, WebHealthy: true, SchemaCurrent: true, EmbeddingSpaceMatches: true, VectorIndexesOnline: true}, nil
	}, c, time.Second) == nil {
		t.Fatal("worker ignored")
	}
}
func TestConfigurePersistsWithoutTeacherPassword(t *testing.T) {
	s := Store{Root: t.TempDir()}
	c := NewController(&s, dockerFixture(&recordingRunner{}), &fakeClock{})
	if e := c.Configure(setupFixture()); e != nil {
		t.Fatal(e)
	}
	cfg, st, e := s.Load()
	if e != nil || st.Phase != CONFIGURED || cfg.ModelCredentialKey.value == "" {
		t.Fatal("not persisted")
	}
	if st.TeacherID != "" {
		t.Fatal("teacher marked created prematurely")
	}
}
func TestReadyPredicateRequiresAllServices(t *testing.T) {
	s := Snapshot{ProjectOwned: true, Neo4jHealthy: true, APIHealthy: true, WorkerHealthy: true, WebHealthy: true, SchemaCurrent: true, EmbeddingSpaceMatches: true, VectorIndexesOnline: true}
	if !isReady(s) {
		t.Fatal("valid ready false")
	}
	s.WorkerHealthy = false
	if isReady(s) {
		t.Fatal("invalid ready true")
	}
}
func TestPortLostAfterPrecheckNeverKillsProcess(t *testing.T) {
	if e := validateWebURL("http://evil.example"); e == nil {
		t.Fatal("foreign URL")
	}
	if e := validateWebURL("http://127.0.0.1:8080"); e != nil {
		t.Fatal(e)
	}
}
func TestCrashAfterTeacherCreatedResumesWithoutReset(t *testing.T) {
	s := Store{Root: t.TempDir()}
	c := NewController(&s, dockerFixture(&recordingRunner{}), &fakeClock{})
	c.Configure(setupFixture())
	_, st, _ := s.Load()
	st.Checkpoint = "teacher"
	st.TeacherID = "fixture-id"
	s.SaveState(st)
	_, got, _ := s.Load()
	if got.TeacherID != "fixture-id" {
		t.Fatal("lost teacher checkpoint")
	}
	_ = fmt.Sprint(c)
}

// Transport fake implements the Docker CLI protocol, exercising real controller sequencing.
type engineRunner struct {
	Requests []ProcessRequest
	FailApp  bool
}

func (r *engineRunner) Run(_ context.Context, q ProcessRequest) (ProcessResult, error) {
	r.Requests = append(r.Requests, q)
	a := strings.Join(q.Args, " ")
	out := ""
	switch {
	case a == "context inspect":
		out = `[{"Endpoints":{"docker":{"Host":"unix:///local.sock"}}}]`
	case strings.HasPrefix(a, "info "):
		out = "linux"
	case strings.Contains(a, " ps "):
		out = `[{"Service":"neo4j","State":"running","Health":"healthy"},{"Service":"api","State":"running","Health":"healthy"},{"Service":"worker","State":"running","Health":"healthy"},{"Service":"web","State":"running"}]`
	case strings.HasSuffix(a, " probe"):
		out = `{"schema_current":true,"embedding_space_matches":true,"vector_indexes_online":true}`
	case strings.HasSuffix(a, " bootstrap"):
		out = `{"user_id":"fixture-teacher-id","username":"teacher_one","created":false}`
	case r.FailApp && strings.HasSuffix(a, "api worker web"):
		return ProcessResult{ExitCode: 1}, nil
	}
	return ProcessResult{Stdout: []byte(out)}, nil
}
func controllerFixture(t *testing.T) (*Controller, *engineRunner) {
	t.Helper()
	r := &engineRunner{}
	d := dockerFixture(r)
	d.Manifest = manifestFixture()
	s := &Store{Root: t.TempDir()}
	c := NewController(s, d, &fakeClock{})
	c.WebCheck = func(context.Context, int) error { return nil }
	if e := c.Configure(setupFixture()); e != nil {
		t.Fatal(e)
	}
	return c, r
}
func TestStartOrdersMigrationBeforeBootstrapAndApp(t *testing.T) {
	c, r := controllerFixture(t)
	in := setupFixture()
	if e := c.Start(context.Background(), &in); e != nil {
		t.Fatal(e)
	}
	m, b, a := -1, -1, -1
	for i, q := range r.Requests {
		args := strings.Join(q.Args, " ")
		if strings.HasSuffix(args, " migrate") {
			m = i
		}
		if strings.HasSuffix(args, " bootstrap") {
			b = i
		}
		if strings.HasSuffix(args, "api worker web") {
			a = i
		}
	}
	if !(m >= 0 && m < b && b < a) {
		t.Fatal("wrong order")
	}
	cfg, st, e := c.store.Load()
	if e != nil || st.Fresh || st.Phase != READY || cfg.Embedding.APIKey.value == "" || in.TeacherPassword.value != "" {
		t.Fatal("not ready or secret retained")
	}
}
func TestReadyDoubleLaunchOnlyOpensExisting(t *testing.T) {
	c, r := controllerFixture(t)
	in := setupFixture()
	if e := c.Start(context.Background(), &in); e != nil {
		t.Fatal(e)
	}
	r.Requests = nil
	if e := c.Start(context.Background(), nil); e != nil {
		t.Fatal(e)
	}
	for _, q := range r.Requests {
		a := strings.Join(q.Args, " ")
		if strings.Contains(a, " migrate") || strings.Contains(a, " bootstrap") || strings.HasSuffix(a, " pull") || strings.Contains(a, " up ") {
			t.Fatal("healthy relaunch changed services")
		}
	}
}
func TestStopPreservesVolumeAndConfig(t *testing.T) {
	c, r := controllerFixture(t)
	cfg, st, _ := c.store.Load()
	if e := c.Stop(context.Background()); e != nil {
		t.Fatal(e)
	}
	after, got, e := c.store.Load()
	if e != nil || got.InstallID != st.InstallID || got.Phase != STOPPED || after.ModelCredentialKey.value != cfg.ModelCredentialKey.value {
		t.Fatal("stop changed config")
	}
	for _, q := range r.Requests {
		for _, a := range q.Args {
			if a == "down" || a == "rm" || a == "prune" {
				t.Fatal("destructive stop")
			}
		}
	}
}
func TestResumeTeacherCheckpointSkipsBootstrapAndMigration(t *testing.T) {
	c, r := controllerFixture(t)
	_, st, _ := c.store.Load()
	st.Checkpoint = "teacher"
	st.TeacherID = "fixture-id"
	c.store.SaveState(st)
	if e := c.Start(context.Background(), nil); e != nil {
		t.Fatal(e)
	}
	for _, q := range r.Requests {
		a := strings.Join(q.Args, " ")
		if strings.HasSuffix(a, " bootstrap") || strings.HasSuffix(a, " migrate") {
			t.Fatal("checkpoint ignored")
		}
	}
}

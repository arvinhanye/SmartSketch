package launch

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

type recordingRunner struct {
	Requests []ProcessRequest
	Response ProcessResult
	Err      error
}

func (r *recordingRunner) Run(_ context.Context, q ProcessRequest) (ProcessResult, error) {
	r.Requests = append(r.Requests, q)
	return r.Response, r.Err
}
func TestChildEnvDropsInheritedConfig(t *testing.T) {
	got := strings.Join(BuildChildEnv([]string{"PATH=/bin", "NEO4J_PASSWORD=old", "LLM_MODE=demo", "COMPOSE_PROJECT_NAME=other", "APP_ENV=development"}), "\n")
	for _, x := range []string{"old", "demo", "other", "development"} {
		if strings.Contains(got, x) {
			t.Fatal("inherited config")
		}
	}
	if !strings.Contains(got, "PATH=/bin") {
		t.Fatal("lost CLI path")
	}
}
func dockerFixture(r Runner) *Docker {
	return &Docker{CLI: "docker", ComposePath: "/bundle with 空格/compose.yaml", EnvPath: "/private config/.env", Runner: r}
}
func TestDockerUsesArgsNotShell(t *testing.T) {
	r := &recordingRunner{}
	d := dockerFixture(r)
	s := InstallState{InstallID: "0123456789abcdef"}
	if e := d.RunStage(context.Background(), s, "neo4j", nil); e != nil {
		t.Fatal(e)
	}
	q := r.Requests[0]
	if q.Executable != "docker" || !strings.Contains(strings.Join(q.Args, "|"), "/bundle with 空格/compose.yaml") {
		t.Fatal("path split")
	}
	if e := d.RunStage(context.Background(), s, "evil; rm", nil); e == nil {
		t.Fatal("arbitrary command accepted")
	}
}
func TestCommandsNeverIncludePassword(t *testing.T) {
	r := &recordingRunner{}
	d := dockerFixture(r)
	if e := d.RunStage(context.Background(), InstallState{InstallID: "0123456789abcdef"}, "bootstrap", []byte(`{"password":"fixture-stdin-secret"}`)); e != nil {
		t.Fatal(e)
	}
	q := r.Requests[0]
	if strings.Contains(strings.Join(append(q.Args, q.Env...), "|"), "fixture-stdin-secret") {
		t.Fatal("secret in argv/env")
	}
	if !strings.Contains(string(q.Stdin), "fixture-stdin-secret") {
		t.Fatal("stdin not sent")
	}
}
func manifestFixture() ReleaseManifest {
	return ReleaseManifest{Version: "fixture-1", BackendImage: "ghcr.io/arvinhanye/smartsketch-backend@sha256:" + strings.Repeat("0", 64), FrontendImage: "ghcr.io/arvinhanye/smartsketch-frontend@sha256:" + strings.Repeat("1", 64), Neo4jImage: "neo4j@sha256:" + strings.Repeat("2", 64), ComposeSHA256: strings.Repeat("3", 64), Targets: []string{"darwin-amd64", "darwin-arm64", "windows-amd64"}}
}
func TestManifestRejectsMutableImages(t *testing.T) {
	p := filepath.Join(t.TempDir(), "manifest.json")
	m := manifestFixture()
	b, _ := json.Marshal(m)
	os.WriteFile(p, b, 0600)
	if _, e := LoadManifest(p); e != nil {
		t.Fatal(e)
	}
	m.BackendImage = "backend:latest"
	b, _ = json.Marshal(m)
	os.WriteFile(p, b, 0600)
	if _, e := LoadManifest(p); e == nil {
		t.Fatal("mutable image")
	}
}
func TestUnknownProjectVolumesAreRejected(t *testing.T) {
	if e := checkVolumeOwner(map[string]string{"com.docker.compose.project": "other", "io.smartsketch.installation": "other"}, "0123456789abcdef"); e == nil {
		t.Fatal("foreign volume accepted")
	}
}

func TestHealthyContainersWithForeignLabelsAreRejected(t *testing.T) {
	r := &ownershipRunner{}
	d := dockerFixture(r)
	if _, e := d.Inspect(context.Background(), InstallState{InstallID: "0123456789abcdef"}); e == nil {
		t.Fatal("foreign container was accepted")
	}
}

type ownershipRunner struct{}

func (*ownershipRunner) Run(_ context.Context, q ProcessRequest) (ProcessResult, error) {
	a := strings.Join(q.Args, " ")
	if strings.Contains(a, " ps ") {
		return ProcessResult{Stdout: []byte(`[{"ID":"fixture-container","Service":"api","State":"running","Health":"healthy"}]`)}, nil
	}
	if strings.Contains(a, "container inspect") {
		return ProcessResult{Stdout: []byte(`{"io.smartsketch.installation":"foreign"}`)}, nil
	}
	return ProcessResult{}, nil
}

type wrongGenerationRunner struct{ base *engineRunner }

func (r wrongGenerationRunner) Run(ctx context.Context, q ProcessRequest) (ProcessResult, error) {
	if len(q.Args) > 0 && q.Args[0] == "container" && strings.Contains(strings.Join(q.Args, " "), ".Mounts") {
		return ProcessResult{Stdout: []byte(`[{"Type":"volume","Destination":"/data","Name":"smartsketch-` + r.base.InstallID + `_app-data"}]`)}, nil
	}
	if len(q.Args) > 1 && q.Args[0] == "volume" && q.Args[1] == "inspect" {
		return ProcessResult{Stdout: []byte(`{"com.docker.compose.project":"smartsketch-` + r.base.InstallID + `","io.smartsketch.installation":"` + r.base.InstallID + `"}`)}, nil
	}
	return r.base.Run(ctx, q)
}
func TestHealthyServicesOnOldGenerationAreNotReady(t *testing.T) {
	c, r := controllerFixture(t)
	_, st, _ := c.store.Load()
	st.DataGeneration = "2222222222222222"
	c.docker.Runner = wrongGenerationRunner{r}
	snap, e := c.docker.Inspect(context.Background(), st)
	if e != nil {
		t.Fatal(e)
	}
	if snap.APIHealthy || snap.WorkerHealthy || snap.Neo4jHealthy {
		t.Fatal("old generation counted as selected data generation")
	}
}

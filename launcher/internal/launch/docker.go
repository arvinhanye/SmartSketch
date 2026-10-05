package launch

import (
	"context"
	"encoding/json"
	"path/filepath"
	"strings"
	"time"
)

type Docker struct {
	CLI, ComposePath, EnvPath string
	Manifest                  ReleaseManifest
	Runner                    Runner
}
type Snapshot struct {
	ProjectOwned                                              bool
	Neo4jHealthy, APIHealthy, WorkerHealthy, WebHealthy       bool
	MigrateExitCode                                           *int
	SchemaCurrent, EmbeddingSpaceMatches, VectorIndexesOnline bool
}

func (d *Docker) run(ctx context.Context, args []string, stdin []byte) (ProcessResult, error) {
	if d.Runner == nil {
		d.Runner = ExecRunner{}
	}
	env := append(childEnv(), "BACKUP_DIR="+filepath.Join(filepath.Dir(d.EnvPath), "backups"))
	for _, a := range args {
		if strings.HasPrefix(a, "smartsketch-") && idPattern.MatchString(strings.TrimPrefix(a, "smartsketch-")) {
			env = append(env, "INSTALL_ID="+strings.TrimPrefix(a, "smartsketch-"), "BACKEND_IMAGE="+d.Manifest.BackendImage, "FRONTEND_IMAGE="+d.Manifest.FrontendImage, "NEO4J_IMAGE="+d.Manifest.Neo4jImage)
			break
		}
	}
	isPull := len(args) > 0 && args[len(args)-1] == "pull"
	if !isPull {
		var cancel context.CancelFunc
		ctx, cancel = context.WithTimeout(ctx, 180*time.Second)
		defer cancel()
	}
	r, e := d.Runner.Run(ctx, ProcessRequest{d.CLI, args, env, stdin})
	if e != nil || r.ExitCode != 0 {
		return r, fail("PROCESS", "docker")
	}
	return r, nil
}
func project(s InstallState) (string, error) {
	if !idPattern.MatchString(s.InstallID) {
		return "", fail("OWNERSHIP", "project")
	}
	return "smartsketch-" + s.InstallID, nil
}
func (d *Docker) compose(s InstallState, args ...string) ([]string, error) {
	p, e := project(s)
	if e != nil {
		return nil, e
	}
	base := []string{"compose", "--project-name", p, "--project-directory", filepath.Dir(d.EnvPath), "--env-file", d.EnvPath, "-f", d.ComposePath}
	if s.DataGeneration != "" {
		if !idPattern.MatchString(s.DataGeneration) {
			return nil, fail("OWNERSHIP", "volume")
		}
		base = append(base, "-f", filepath.Join(filepath.Dir(d.EnvPath), "volumes.json"))
	}
	return append(base, args...), nil
}
func (d *Docker) RunStage(ctx context.Context, s InstallState, stage string, stdin []byte) error {
	var args []string
	switch stage {
	case "neo4j":
		args = []string{"up", "-d", "neo4j"}
	case "migrate", "bootstrap", "probe":
		args = []string{"run", "--rm", "--no-deps", "-T", stage}
	case "app":
		args = []string{"up", "-d", "--no-deps", "api", "worker", "web"}
	default:
		return fail("PROCESS", "stage")
	}
	q, e := d.compose(s, args...)
	if e != nil {
		return e
	}
	_, e = d.run(ctx, q, stdin)
	return e
}
func (d *Docker) Pull(ctx context.Context, s InstallState) error {
	q, e := d.compose(s, "--profile", "tools", "pull")
	if e != nil {
		return e
	}
	_, e = d.run(ctx, q, nil)
	return e
}
func (d *Docker) Stop(ctx context.Context, s InstallState) error {
	q, e := d.compose(s, "stop", "-t", "90", "web", "api", "worker", "neo4j")
	if e != nil {
		return e
	}
	_, e = d.run(ctx, q, nil)
	return e
}
func checkVolumeOwner(labels map[string]string, id string) error {
	if labels["com.docker.compose.project"] != "smartsketch-"+id || labels["io.smartsketch.installation"] != id {
		return fail("OWNERSHIP", "volume")
	}
	return nil
}
func (d *Docker) CheckEngine(ctx context.Context) error {
	r, e := d.run(ctx, []string{"context", "inspect"}, nil)
	if e != nil {
		return fail("DOCKER", "environment")
	}
	var contexts []struct {
		Endpoints map[string]struct{ Host string }
	}
	if json.Unmarshal(r.Stdout, &contexts) != nil || len(contexts) != 1 {
		return fail("DOCKER", "context")
	}
	h := contexts[0].Endpoints["docker"].Host
	if !strings.HasPrefix(h, "unix://") && !strings.HasPrefix(h, "npipe://") {
		return fail("DOCKER", "remote")
	}
	r, e = d.run(ctx, []string{"info", "--format", "{{.OSType}}"}, nil)
	if e != nil || strings.TrimSpace(string(r.Stdout)) != "linux" {
		return fail("DOCKER", "engine")
	}
	return nil
}
func (d *Docker) Inspect(ctx context.Context, s InstallState) (Snapshot, error) {
	p, e := project(s)
	if e != nil {
		return Snapshot{}, e
	}
	snap := Snapshot{ProjectOwned: true}
	r, e := d.run(ctx, []string{"volume", "ls", "--filter", "name=^" + p + "_", "--format", "{{.Name}}"}, nil)
	if e != nil {
		return snap, e
	}
	for _, name := range strings.Fields(string(r.Stdout)) {
		r, e := d.run(ctx, []string{"volume", "inspect", name, "--format", "{{json .Labels}}"}, nil)
		if e != nil {
			return snap, e
		}
		var labels map[string]string
		if json.Unmarshal(r.Stdout, &labels) != nil || checkVolumeOwner(labels, s.InstallID) != nil {
			return Snapshot{}, fail("OWNERSHIP", "volume")
		}
	}
	q, e := d.compose(s, "ps", "--all", "--format", "json")
	if e != nil {
		return snap, e
	}
	r, e = d.run(ctx, q, nil)
	if e != nil {
		return snap, e
	}
	var rows []struct{ Service, State, Health string }
	trim := strings.TrimSpace(string(r.Stdout))
	if strings.HasPrefix(trim, "[") {
		if json.Unmarshal(r.Stdout, &rows) != nil {
			return snap, fail("PROCESS", "inspect")
		}
	} else {
		for _, line := range strings.Split(trim, "\n") {
			if line == "" {
				continue
			}
			var row struct{ Service, State, Health string }
			if json.Unmarshal([]byte(line), &row) != nil {
				return snap, fail("PROCESS", "inspect")
			}
			rows = append(rows, row)
		}
	}
	for _, row := range rows {
		healthy := row.State == "running" && row.Health == "healthy"
		switch row.Service {
		case "neo4j":
			snap.Neo4jHealthy = healthy
		case "api":
			snap.APIHealthy = healthy
		case "worker":
			snap.WorkerHealthy = healthy
		case "web":
			snap.WebHealthy = row.State == "running"
		}
	}
	return snap, nil
}
func (d *Docker) Probe(ctx context.Context, s InstallState) (Snapshot, error) {
	q, e := d.compose(s, "run", "--rm", "--no-deps", "-T", "probe")
	if e != nil {
		return Snapshot{}, e
	}
	r, e := d.run(ctx, q, nil)
	if e != nil {
		return Snapshot{}, e
	}
	var v struct {
		Schema  bool `json:"schema_current"`
		Space   bool `json:"embedding_space_matches"`
		Indexes bool `json:"vector_indexes_online"`
	}
	if strictJSON(r.Stdout, &v) != nil {
		return Snapshot{}, fail("HEALTH", "probe")
	}
	return Snapshot{SchemaCurrent: v.Schema, EmbeddingSpaceMatches: v.Space, VectorIndexesOnline: v.Indexes}, nil
}

type BootstrapResult struct {
	UserID   string `json:"user_id"`
	Username string `json:"username"`
	Created  bool   `json:"created"`
}

func (d *Docker) Bootstrap(ctx context.Context, s InstallState, stdin []byte) (BootstrapResult, error) {
	q, e := d.compose(s, "run", "--rm", "--no-deps", "-T", "bootstrap")
	if e != nil {
		return BootstrapResult{}, e
	}
	r, e := d.run(ctx, q, stdin)
	if e != nil {
		return BootstrapResult{}, e
	}
	var result BootstrapResult
	if strictJSON(r.Stdout, &result) != nil || result.UserID == "" || result.Username != s.TeacherUsername {
		return result, fail("PROCESS", "teacher")
	}
	return result, nil
}

package launch

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"strconv"
	"sync"
	"time"
)

type StatusView struct {
	WebPort          int      `json:"web_port,omitempty"`
	NeedsUpgrade     bool     `json:"needs_upgrade"`
	PendingUpgradeID string   `json:"pending_upgrade_id,omitempty"`
	NeedsTeacher     bool     `json:"needs_teacher"`
	Phase            Phase    `json:"phase"`
	Stage            string   `json:"stage"`
	WebURL           string   `json:"web_url,omitempty"`
	Busy             bool     `json:"busy"`
	Failure          *Failure `json:"failure,omitempty"`
	Actions          []string `json:"actions"`
	AccountNotice    string   `json:"account_notice,omitempty"`
}
type Controller struct {
	store     *Store
	docker    *Docker
	clock     Clock
	operation sync.Mutex
	mu        sync.Mutex
	view      StatusView
	WebCheck  func(context.Context, int) error
}

func NewController(s *Store, d *Docker, clock Clock) *Controller {
	if clock == nil {
		clock = wallClock{}
	}
	return &Controller{store: s, docker: d, clock: clock, WebCheck: checkWeb, view: StatusView{Phase: NEW}}
}
func portString(p int) string { return strconv.Itoa(p) }
func webURL(p int) string     { return "http://127.0.0.1:" + portString(p) }
func (c *Controller) Configure(in SetupInput) error {
	if !c.operation.TryLock() {
		return fail("LOCK", "operation")
	}
	defer c.operation.Unlock()
	_, old, e := c.store.Load()
	if e != nil {
		return e
	}
	if old.Phase != NEW {
		return fail("CONFIG", "existing")
	}
	cfg, e := NewConfig(in, rand.Reader)
	if e != nil {
		return e
	}
	id := make([]byte, 8)
	if _, e = rand.Read(id); e != nil {
		return fail("CONFIG", "random")
	}
	st := InstallState{SchemaVersion: 1, InstallID: hex.EncodeToString(id), ReleaseVersion: c.docker.Manifest.Version, Phase: CONFIGURED, WebPort: cfg.WebPort, Fresh: true, TeacherUsername: in.TeacherUsername}
	return c.store.SaveConfig(cfg, st)
}
func (c *Controller) setStage(stage string) {
	c.mu.Lock()
	c.view.Stage = stage
	c.view.Busy = true
	c.mu.Unlock()
}
func (c *Controller) Start(ctx context.Context, in *SetupInput) (err error) {
	if !c.operation.TryLock() {
		return fail("LOCK", "operation")
	}
	defer c.operation.Unlock()
	cfg, st, e := c.store.Load()
	if e != nil {
		return e
	}
	if st.Phase == NEW {
		return fail("CONFIG", "setup")
	}
	if st.ReleaseVersion != c.docker.Manifest.Version {
		return fail("VERSION", "upgrade")
	}
	c.mu.Lock()
	c.view = StatusView{Phase: INITIALIZING, Stage: "environment", Busy: true}
	c.mu.Unlock()
	defer func() {
		c.mu.Lock()
		c.view.Busy = false
		if err != nil {
			var f *Failure
			if !errors.As(err, &f) {
				f = fail("PROCESS", c.view.Stage)
			}
			c.view.Failure = f
			c.view.Phase = ERROR
			st.Phase = ERROR
		} else {
			c.view.Phase = READY
			c.view.WebURL = webURL(cfg.WebPort)
			st.Phase = READY
		}
		c.mu.Unlock()
		if e := c.store.SaveState(st); err == nil && e != nil {
			err = e
		}
	}()
	if e = c.docker.CheckEngine(ctx); e != nil {
		return e
	}
	snap, e := c.docker.Inspect(ctx, st)
	if e != nil {
		return e
	}
	if !st.Fresh && isReadyWithProbe(ctx, c, snap, st) {
		return nil
	}
	if !snap.WebHealthy {
		if e = checkPort(cfg.WebPort); e != nil {
			return e
		}
	}
	if st.Fresh && st.TeacherID == "" {
		if in == nil || ValidateSetup(*in) != nil || in.TeacherUsername != st.TeacherUsername {
			return fail("FIELD", "teacher")
		}
	}
	if st.Fresh {
		c.setStage("pull")
		if e = c.docker.Pull(ctx, st); e != nil {
			return e
		}
	}
	ctx, cancel := context.WithTimeout(ctx, 180*time.Second)
	defer cancel()
	deadline := c.clock.Now().Add(180 * time.Second)
	c.setStage("neo4j")
	if e = c.docker.RunStage(ctx, st, "neo4j", nil); e != nil {
		return e
	}
	if e = WaitReady(ctx, func(ctx context.Context) (Snapshot, error) {
		s, e := c.docker.Inspect(ctx, st)
		if e != nil {
			return s, e
		}
		return Snapshot{ProjectOwned: s.ProjectOwned, Neo4jHealthy: s.Neo4jHealthy, APIHealthy: true, WorkerHealthy: true, WebHealthy: true, SchemaCurrent: true, EmbeddingSpaceMatches: true, VectorIndexesOnline: true}, nil
	}, c.clock, deadline.Sub(c.clock.Now())); e != nil {
		return e
	}
	if st.Fresh && st.Checkpoint != "migrated" && st.Checkpoint != "teacher" {
		c.setStage("migrate")
		if e = c.docker.RunStage(ctx, st, "migrate", nil); e != nil {
			return e
		}
		st.Checkpoint = "migrated"
		st.Phase = INITIALIZING
		if e = c.store.SaveState(st); e != nil {
			return e
		}
	}
	if st.Fresh && st.TeacherID == "" {
		c.setStage("teacher")
		payload, _ := json.Marshal(map[string]string{"username": in.TeacherUsername, "password": in.TeacherPassword.value})
		result, e := c.docker.Bootstrap(ctx, st, payload)
		clear(payload)
		in.TeacherPassword = Secret{}
		in.ConfirmPassword = Secret{}
		if e != nil {
			return e
		}
		st.TeacherID = result.UserID
		st.Checkpoint = "teacher"
		if !result.Created {
			c.mu.Lock()
			c.view.AccountNotice = "账号已存在，仍使用首次口令。"
			c.mu.Unlock()
		}
		if e = c.store.SaveState(st); e != nil {
			return e
		}
	}
	c.setStage("app")
	if e = c.docker.RunStage(ctx, st, "app", nil); e != nil {
		if checkPort(cfg.WebPort) != nil {
			return fail("PORT", "web")
		}
		return e
	}
	c.setStage("readiness")
	e = WaitReady(ctx, func(ctx context.Context) (Snapshot, error) {
		s, e := c.docker.Inspect(ctx, st)
		if e != nil {
			return s, e
		}
		if s.Neo4jHealthy && s.APIHealthy && s.WorkerHealthy && s.WebHealthy {
			if e = mergeProbe(ctx, c.docker, st, &s); e != nil {
				return s, e
			}
			if c.WebCheck(ctx, cfg.WebPort) != nil {
				s.WebHealthy = false
			}
		}
		return s, nil
	}, c.clock, deadline.Sub(c.clock.Now()))
	if e != nil {
		return e
	}
	st.Fresh = false
	st.Checkpoint = "ready"
	return nil
}
func isReadyWithProbe(ctx context.Context, c *Controller, s Snapshot, st InstallState) bool {
	if !(s.ProjectOwned && s.Neo4jHealthy && s.APIHealthy && s.WorkerHealthy && s.WebHealthy) {
		return false
	}
	return mergeProbe(ctx, c.docker, st, &s) == nil && isReady(s) && c.WebCheck(ctx, st.WebPort) == nil
}
func (c *Controller) Stop(ctx context.Context) error {
	if !c.operation.TryLock() {
		return fail("LOCK", "operation")
	}
	defer c.operation.Unlock()
	_, st, e := c.store.Load()
	if e != nil {
		return e
	}
	if st.Phase == NEW {
		return fail("CONFIG", "setup")
	}
	if _, e = c.docker.Inspect(ctx, st); e != nil {
		return e
	}
	c.setStage("stopping")
	defer func() { c.mu.Lock(); c.view.Busy = false; c.mu.Unlock() }()
	if e = c.docker.Stop(ctx, st); e != nil {
		return e
	}
	st.Phase = STOPPED
	if e = c.store.SaveState(st); e != nil {
		return e
	}
	c.mu.Lock()
	c.view = StatusView{Phase: STOPPED, Stage: "stopped"}
	c.mu.Unlock()
	return nil
}
func (c *Controller) Status(ctx context.Context) (StatusView, error) {
	c.mu.Lock()
	v := c.view
	c.mu.Unlock()
	if !v.Busy {
		if !c.operation.TryLock() {
			v.Busy = true
			v.Actions = []string{}
			return v, nil
		}
		defer c.operation.Unlock()
		_, st, e := c.store.Load()
		if e != nil {
			return v, e
		}
		v.Phase = st.Phase
		v.WebPort = st.WebPort
		v.NeedsTeacher = st.Fresh && st.TeacherID == ""
		v.NeedsUpgrade = st.Phase != NEW && st.ReleaseVersion != c.docker.Manifest.Version
		if v.NeedsUpgrade {
			b, e := os.ReadFile(filepath.Join(c.store.Root, "upgrade.json"))
			if e == nil {
				var pending struct {
					ID     string `json:"backup_id"`
					Target string `json:"target_version"`
				}
				if strictJSON(b, &pending) == nil && idPattern.MatchString(pending.ID) && pending.Target == c.docker.Manifest.Version {
					v.PendingUpgradeID = pending.ID
				}
			}
		}
		if st.Phase == READY {
			snap, e := c.docker.Inspect(ctx, st)
			if e != nil || !isReadyWithProbe(ctx, c, snap, st) {
				v.Phase = ERROR
				v.Failure = fail("HEALTH", "readiness")
			} else {
				v.WebURL = webURL(st.WebPort)
			}
		}
	}
	v.Actions = []string{}
	if !v.Busy {
		if v.Phase == NEW {
			v.Actions = append(v.Actions, "setup")
		} else {
			v.Actions = append(v.Actions, "start", "stop", "diagnostics", "restore", "port")
			if v.NeedsUpgrade {
				v.Actions = append(v.Actions, "upgrade")
			}
			if v.Phase == READY {
				v.Actions = append(v.Actions, "open")
			}
		}
	}
	return v, nil
}

func mergeProbe(ctx context.Context, d *Docker, st InstallState, s *Snapshot) error {
	p, e := d.Probe(ctx, st)
	s.SchemaCurrent = p.SchemaCurrent
	s.EmbeddingSpaceMatches = p.EmbeddingSpaceMatches
	s.VectorIndexesOnline = p.VectorIndexesOnline
	return e
}

func (c *Controller) recordFailure(e error) {
	var f *Failure
	if !errors.As(e, &f) {
		f = fail("PROCESS", "control")
	}
	c.mu.Lock()
	c.view.Failure = f
	c.view.Stage = f.Stage
	c.view.Phase = ERROR
	c.view.Busy = false
	c.mu.Unlock()
	_, st, loadErr := c.store.Load()
	if loadErr == nil && st.Phase != NEW {
		st.Phase = ERROR
		_ = c.store.SaveState(st)
	}
}

// ChangePort stops only the owned installation after explicit confirmation. Secrets,
// account metadata and the selected data generation remain unchanged.
func (c *Controller) ChangePort(ctx context.Context, port int, confirmed bool) error {
	if !confirmed {
		return fail("FIELD", "confirmation")
	}
	if port < 1024 || port > 65535 {
		return fail("FIELD", "port")
	}
	if !c.operation.TryLock() {
		return fail("LOCK", "operation")
	}
	defer c.operation.Unlock()
	cfg, st, e := c.store.Load()
	if e != nil {
		return e
	}
	if st.Phase == NEW {
		return fail("CONFIG", "setup")
	}
	if port == cfg.WebPort {
		return nil
	}
	if e = checkPort(port); e != nil {
		return e
	}
	if _, e = c.docker.Inspect(ctx, st); e != nil {
		return e
	}
	if e = c.docker.Stop(ctx, st); e != nil {
		return e
	}
	cfg.WebPort = port
	st.WebPort = port
	st.Phase = STOPPED
	if st.Fresh {
		st.Phase = CONFIGURED
	}
	if e = c.store.SaveConfig(cfg, st); e != nil {
		return e
	}
	c.mu.Lock()
	c.view = StatusView{Phase: st.Phase, Stage: "stopped", WebPort: port}
	c.mu.Unlock()
	return nil
}

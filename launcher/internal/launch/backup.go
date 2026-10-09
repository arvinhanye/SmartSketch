package launch

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"io"
	"os"
	"path/filepath"
	"strings"
)

type BackupSet struct {
	ID, InstallID, ReleaseVersion, ManifestSHA256 string
	Files                                         map[string]string
}

var backupNames = []string{".env", "installation.json", "compose.yaml", "release-manifest.json", "app.tar.gz", "neo4j.tar.gz", "neo4j-logs.tar.gz"}

func newID() (string, error) {
	b := make([]byte, 8)
	if _, e := rand.Read(b); e != nil {
		return "", fail("BACKUP", "random")
	}
	return hex.EncodeToString(b), nil
}
func fileSHA(path string) (string, error) {
	if noLinks(path) != nil {
		return "", fail("BACKUP", "path")
	}
	f, e := os.Open(path)
	if e != nil {
		return "", fail("BACKUP", "file")
	}
	defer f.Close()
	hash := sha256.New()
	if _, e = io.Copy(hash, f); e != nil {
		return "", fail("BACKUP", "file")
	}
	return hex.EncodeToString(hash.Sum(nil)), nil
}
func (c *Controller) backupPath(id string) (string, error) {
	if !idPattern.MatchString(id) {
		return "", fail("BACKUP", "identity")
	}
	p := filepath.Join(c.store.Root, "backups", id)
	if noLinks(p) != nil {
		return "", fail("BACKUP", "path")
	}
	return p, nil
}
func (c *Controller) verifyBackup(set BackupSet) (Config, InstallState, ReleaseManifest, error) {
	cfg, current, e := c.store.Load()
	if e != nil {
		return cfg, current, ReleaseManifest{}, e
	}
	if set.InstallID != current.InstallID || !idPattern.MatchString(set.ID) || len(set.Files) != len(backupNames) {
		return Config{}, InstallState{}, ReleaseManifest{}, fail("BACKUP", "identity")
	}
	root, e := c.backupPath(set.ID)
	if e != nil {
		return cfg, current, ReleaseManifest{}, e
	}
	for _, name := range backupNames {
		h, e := fileSHA(filepath.Join(root, name))
		if e != nil || h != set.Files[name] {
			return cfg, current, ReleaseManifest{}, fail("BACKUP", "checksum")
		}
	}
	manifest, e := LoadManifest(filepath.Join(root, "release-manifest.json"))
	if e != nil || manifest.Version != set.ReleaseVersion || set.Files["release-manifest.json"] != set.ManifestSHA256 || manifest.VerifyCompose(filepath.Join(root, "compose.yaml")) != nil {
		return cfg, current, manifest, fail("BACKUP", "manifest")
	}
	snapshot := Store{Root: root}
	restored, st, e := snapshot.Load()
	if e != nil || st.InstallID != current.InstallID || st.ReleaseVersion != manifest.Version || restored.ModelCredentialKey.value != cfg.ModelCredentialKey.value || restored.Neo4jPassword.value != cfg.Neo4jPassword.value {
		return cfg, current, manifest, fail("BACKUP", "key")
	}
	return restored, st, manifest, nil
}

// PrepareUpgrade never migrates. The returned snapshot must be verified and a second action confirmed.
func (c *Controller) PrepareUpgrade(ctx context.Context, target ReleaseManifest, confirmed bool) (BackupSet, error) {
	if !confirmed {
		return BackupSet{}, fail("VERSION", "confirmation")
	}
	if !c.operation.TryLock() {
		return BackupSet{}, fail("LOCK", "operation")
	}
	defer c.operation.Unlock()
	_, st, e := c.store.Load()
	if e != nil {
		return BackupSet{}, e
	}
	if st.Fresh || st.ReleaseVersion == target.Version {
		return BackupSet{}, fail("VERSION", "upgrade")
	}
	old, e := LoadManifest(filepath.Join(c.store.Root, "release-manifest.json"))
	if e != nil || old.Version != st.ReleaseVersion || old.VerifyCompose(filepath.Join(c.store.Root, "compose.yaml")) != nil {
		return BackupSet{}, fail("BACKUP", "manifest")
	}
	d := *c.docker
	d.Manifest = old
	d.ComposePath = filepath.Join(c.store.Root, "compose.yaml")
	if _, e = d.Inspect(ctx, st); e != nil {
		return BackupSet{}, e
	}
	if e = d.Stop(ctx, st); e != nil {
		return BackupSet{}, e
	}
	st.Phase = STOPPED
	if e = c.store.SaveState(st); e != nil {
		return BackupSet{}, e
	}
	id, e := newID()
	if e != nil {
		return BackupSet{}, e
	}
	root, _ := c.backupPath(id)
	snapStore := Store{Root: root}
	if e = snapStore.ensure(); e != nil {
		return BackupSet{}, e
	}
	for _, name := range backupNames[:4] {
		if noLinks(filepath.Join(c.store.Root, name)) != nil {
			return BackupSet{}, fail("BACKUP", "path")
		}
		b, e := os.ReadFile(filepath.Join(c.store.Root, name))
		if e != nil {
			return BackupSet{}, fail("BACKUP", "file")
		}
		if e = snapStore.atomic(name, b); e != nil {
			return BackupSet{}, e
		}
	}
	if e = d.snapshotTool(ctx, st, root, "backup", st.DataGeneration); e != nil {
		return BackupSet{}, e
	}
	set := BackupSet{ID: id, InstallID: st.InstallID, ReleaseVersion: old.Version, Files: map[string]string{}}
	for _, name := range backupNames {
		h, e := fileSHA(filepath.Join(root, name))
		if e != nil {
			return BackupSet{}, e
		}
		set.Files[name] = h
	}
	set.ManifestSHA256 = set.Files["release-manifest.json"]
	if _, _, _, e = c.verifyBackup(set); e != nil {
		return BackupSet{}, e
	}
	b, _ := json.Marshal(set)
	if e = snapStore.atomic("backup.json", b); e != nil {
		return BackupSet{}, e
	}
	pending, _ := json.Marshal(map[string]string{"backup_id": set.ID, "target_version": target.Version})
	if e = c.store.atomic("upgrade.json", pending); e != nil {
		return BackupSet{}, e
	}
	return set, nil
}
func volumeNames(st InstallState, generation string) (map[string]string, error) {
	p, e := project(st)
	if e != nil || generation != "" && !idPattern.MatchString(generation) {
		return nil, fail("OWNERSHIP", "volume")
	}
	suffix := ""
	if generation != "" {
		suffix = "-" + generation
	}
	return map[string]string{"app": p + "_app-data" + suffix, "neo4j": p + "_neo4j-data" + suffix, "neo4j-logs": p + "_neo4j-logs" + suffix}, nil
}
func (d *Docker) snapshotTool(ctx context.Context, st InstallState, root, mode, generation string) error {
	if mode != "backup" && mode != "restore" {
		return fail("BACKUP", "operation")
	}
	volumes, e := volumeNames(st, generation)
	if e != nil || noLinks(root) != nil {
		return fail("BACKUP", "path")
	}
	args := []string{"run", "--rm", "--network", "none", "--user", "0", "--label", "io.smartsketch.installation=" + st.InstallID}
	for _, name := range []string{"app", "neo4j", "neo4j-logs"} {
		target := "/source/" + name
		ro := ",readonly"
		if mode == "restore" {
			target = "/stage/" + name
			ro = ""
		}
		args = append(args, "--mount", "type=volume,source="+volumes[name]+",target="+target+ro)
	}
	ro := ""
	if mode == "restore" {
		ro = ",readonly"
	}
	if strings.Contains(root, ",") {
		return fail("BACKUP", "path")
	}
	args = append(args, "--mount", "type=bind,source="+root+",target=/backup"+ro, d.Manifest.BackendImage, "python", "-m", "app.tools.install_backup", mode)
	_, e = d.run(ctx, args, nil)
	return e
}
func volumeMapBytes(st InstallState) ([]byte, error) {
	vols, e := volumeNames(st, st.DataGeneration)
	if e != nil {
		return nil, e
	}
	entries := map[string]any{}
	for logical, key := range map[string]string{"app-data": "app", "neo4j-data": "neo4j", "neo4j-logs": "neo4j-logs"} {
		entries[logical] = map[string]string{"name": vols[key]}
	}
	return json.Marshal(map[string]any{"volumes": entries})
}

func writeVolumeMap(s *Store, st InstallState) error {
	b, e := volumeMapBytes(st)
	if e != nil {
		return e
	}
	return s.atomic("volumes.json", b)
}
func restoreGroup(cfg Config, st InstallState, source *Store) (map[string][]byte, error) {
	env, e := EncodeEnv(cfg)
	if e != nil {
		return nil, e
	}
	state, e := json.Marshal(st)
	if e != nil {
		return nil, fail("BACKUP", "state")
	}
	vols, e := volumeMapBytes(st)
	if e != nil {
		return nil, e
	}
	files := map[string][]byte{".env": env, "installation.json": state, "volumes.json": vols}
	for _, name := range []string{"compose.yaml", "release-manifest.json"} {
		b, e := fileContent(source, name)
		if e != nil {
			return nil, e
		}
		files[name] = b
	}
	return files, nil
}

// Restore first stages and checks the snapshot, then awaits a separate confirmation.
// A consumed generation is never offered again: the immutable backup is re-extracted.
// Interrupted candidates resume without mutating the active installation metadata.
func (c *Controller) Restore(ctx context.Context, set BackupSet, confirmed bool) error {
	if !confirmed {
		return fail("BACKUP", "confirmation")
	}
	if !c.operation.TryLock() {
		return fail("LOCK", "operation")
	}
	defer c.operation.Unlock()
	cfg, st, old, e := c.verifyBackup(set)
	if e != nil {
		return e
	}
	_, current, e := c.store.Load()
	if e != nil {
		return e
	}
	root, _ := c.backupPath(set.ID)
	snapshot := Store{Root: root}
	candidate := Store{Root: filepath.Join(c.store.Root, "candidates", set.ID)}
	d := *c.docker
	d.Manifest = old
	d.ComposePath = filepath.Join(candidate.Root, "compose.yaml")
	d.EnvPath = filepath.Join(candidate.Root, ".env")
	candidateCfg, ready, e := candidate.Load()
	if e != nil {
		return e
	}
	reusable := ready.Phase != NEW && ready.DataGeneration != "" && ready.Checkpoint != "restore-consumed" && current.RestoreHistory[set.ID] != ready.DataGeneration
	if ready.Phase != NEW && (ready.InstallID != current.InstallID || ready.DataGeneration == "" || candidateCfg.ModelCredentialKey.value != cfg.ModelCredentialKey.value || candidateCfg.Neo4jPassword.value != cfg.Neo4jPassword.value) {
		return fail("BACKUP", "candidate")
	}
	if reusable && ready.Checkpoint == "restore-verified" {
		snap, inspectErr := d.Inspect(ctx, ready)
		if inspectErr != nil {
			return inspectErr
		}
		if mergeProbe(ctx, &d, ready, &snap) == nil && isReady(snap) && c.WebCheck(ctx, ready.WebPort) == nil {
			ready.RestoreHistory = map[string]string{}
			for id, generation := range current.RestoreHistory {
				ready.RestoreHistory[id] = generation
			}
			ready.RestoreHistory[set.ID] = ready.DataGeneration
			files, e := restoreGroup(cfg, ready, &snapshot)
			if e != nil {
				return e
			}
			if e = c.store.commitGroup(files); e != nil {
				return e
			}
			// The root journal records consumption even if this best-effort marker is interrupted.
			ready.Checkpoint = "restore-consumed"
			_ = candidate.SaveState(ready)
			c.docker.Manifest = old
			c.docker.ComposePath = filepath.Join(c.store.Root, "compose.yaml")
			c.docker.EnvPath = filepath.Join(c.store.Root, ".env")
			c.mu.Lock()
			c.view = StatusView{Phase: READY, Stage: "readiness", WebURL: webURL(ready.WebPort)}
			c.mu.Unlock()
			return nil
		}
	}
	if !reusable {
		if _, e = c.docker.Inspect(ctx, current); e != nil {
			return e
		}
		if e = c.docker.Stop(ctx, current); e != nil {
			return e
		}
		current.Phase = STOPPED
		if e = c.store.SaveState(current); e != nil {
			return e
		}
		generation, e := newID()
		if e != nil {
			return e
		}
		volumes, _ := volumeNames(st, generation)
		for _, name := range []string{"app", "neo4j", "neo4j-logs"} {
			_, e = c.docker.run(ctx, []string{"volume", "create", "--label", "io.smartsketch.installation=" + st.InstallID, "--label", "com.docker.compose.project=smartsketch-" + st.InstallID, volumes[name]}, nil)
			if e != nil {
				return e
			}
			r, e := c.docker.run(ctx, []string{"volume", "inspect", volumes[name], "--format", "{{json .Labels}}"}, nil)
			var labels map[string]string
			if e != nil || json.Unmarshal(r.Stdout, &labels) != nil || checkVolumeOwner(labels, st.InstallID) != nil {
				return fail("OWNERSHIP", "restore-volume")
			}
		}
		if e = d.snapshotTool(ctx, st, root, "restore", generation); e != nil {
			return e
		}
		ready = st
		ready.DataGeneration = generation
		ready.Fresh = false
		ready.Phase = STOPPED
		ready.Checkpoint = "restore-staged"
	}
	// Rebuild fixed assets from the verified backup before resuming a staged candidate.
	files, e := restoreGroup(cfg, ready, &snapshot)
	if e != nil {
		return e
	}
	if e = candidate.commitGroup(files); e != nil {
		return e
	}
	cc := NewController(&candidate, &d, c.clock)
	cc.WebCheck = c.WebCheck
	if e = cc.Start(ctx, nil); e != nil {
		_ = d.Stop(ctx, ready)
		return e
	}
	_, ready, e = candidate.Load()
	if e != nil {
		return e
	}
	ready.Checkpoint = "restore-verified"
	if e = candidate.SaveState(ready); e != nil {
		return e
	}
	return fail("BACKUP", "restore-confirm")
}

func (c *Controller) LoadBackup(id string) (BackupSet, error) {
	root, e := c.backupPath(id)
	if e != nil {
		return BackupSet{}, e
	}
	b, e := os.ReadFile(filepath.Join(root, "backup.json"))
	var set BackupSet
	if e != nil || len(b) > 16384 || strictJSON(b, &set) != nil || set.ID != id {
		return BackupSet{}, fail("BACKUP", "metadata")
	}
	if _, _, _, e = c.verifyBackup(set); e != nil {
		return BackupSet{}, e
	}
	return set, nil
}
func (c *Controller) ApplyUpgrade(ctx context.Context, set BackupSet, confirmed bool) error {
	if !confirmed {
		return fail("VERSION", "confirmation")
	}
	if !c.operation.TryLock() {
		return fail("LOCK", "operation")
	}
	locked := true
	defer func() {
		if locked {
			c.operation.Unlock()
		}
	}()
	_, original, _, e := c.verifyBackup(set)
	if e != nil {
		return e
	}
	_, current, e := c.store.Load()
	if e != nil {
		return e
	}
	if current.InstallID != original.InstallID || current.Phase != STOPPED || current.ReleaseVersion != set.ReleaseVersion || current.ReleaseVersion == c.docker.Manifest.Version {
		return fail("VERSION", "upgrade")
	}
	if c.docker.Manifest.VerifyCompose(c.docker.ComposePath) != nil {
		return fail("MANIFEST", "compose")
	}
	if _, e = c.docker.Inspect(ctx, current); e != nil {
		return e
	}
	// Both groups remain stopped; original snapshots have already passed verification.
	b, e := os.ReadFile(c.docker.ComposePath)
	if e != nil {
		return fail("MANIFEST", "read")
	}
	mb, _ := json.Marshal(c.docker.Manifest)
	current.ReleaseVersion = c.docker.Manifest.Version
	current.Fresh = true
	current.Checkpoint = ""
	current.Phase = CONFIGURED
	state, _ := json.Marshal(current)
	files := map[string][]byte{"compose.yaml": b, "release-manifest.json": mb, "installation.json": state}
	if current.DataGeneration != "" {
		vols, e := volumeMapBytes(current)
		if e != nil {
			return e
		}
		files["volumes.json"] = vols
	}
	if e = c.store.commitGroup(files); e != nil {
		return e
	}

	c.operation.Unlock()
	locked = false
	return c.Start(ctx, nil)
}

package launch

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
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
	b, e := os.ReadFile(path)
	if e != nil {
		return "", fail("BACKUP", "file")
	}
	h := sha256.Sum256(b)
	return hex.EncodeToString(h[:]), nil
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
func writeVolumeMap(s *Store, st InstallState) error {
	vols, e := volumeNames(st, st.DataGeneration)
	if e != nil {
		return e
	}
	entries := map[string]any{}
	for logical, key := range map[string]string{"app-data": "app", "neo4j-data": "neo4j", "neo4j-logs": "neo4j-logs"} {
		entries[logical] = map[string]string{"name": vols[key]}
	}
	b, _ := json.Marshal(map[string]any{"volumes": entries})
	return s.atomic("volumes.json", b)
}

// Restore first stages and checks the snapshot, then awaits a separate confirmation call.
// Original named volumes are never deleted or overwritten.
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
	candidateRoot := filepath.Join(c.store.Root, "candidates", set.ID)
	candidate := Store{Root: candidateRoot}
	candidateStateFile := filepath.Join(candidateRoot, "installation.json")
	if b, e := os.ReadFile(candidateStateFile); e == nil {
		var ready InstallState
		if strictJSON(b, &ready) != nil || ready.Checkpoint != "restore-verified" || ready.InstallID != current.InstallID || ready.DataGeneration == "" {
			return fail("BACKUP", "candidate")
		}
		d := *c.docker
		d.Manifest = old
		d.ComposePath = filepath.Join(candidateRoot, "compose.yaml")
		d.EnvPath = filepath.Join(candidateRoot, ".env")
		s, e := d.Inspect(ctx, ready)
		if e != nil || mergeProbe(ctx, &d, ready, &s) != nil || !isReady(s) || c.WebCheck(ctx, ready.WebPort) != nil {
			return fail("BACKUP", "candidate-health")
		}
		if e = c.store.SaveConfig(cfg, ready); e != nil {
			return e
		}
		for _, name := range []string{"compose.yaml", "release-manifest.json", "volumes.json"} {
			b, e := os.ReadFile(filepath.Join(candidateRoot, name))
			if e != nil {
				return fail("BACKUP", "candidate")
			}
			if e = c.store.atomic(name, b); e != nil {
				return e
			}
		}
		c.docker.Manifest = old
		c.docker.ComposePath = filepath.Join(c.store.Root, "compose.yaml")
		return nil
	}
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
	}
	d := *c.docker
	d.Manifest = old
	if e = d.snapshotTool(ctx, st, root, "restore", generation); e != nil {
		return e
	}
	st.DataGeneration = generation
	st.Fresh = false
	st.Phase = STOPPED
	st.Checkpoint = "restore-staged"
	if e = candidate.SaveConfig(cfg, st); e != nil {
		return e
	}
	for _, name := range []string{"compose.yaml", "release-manifest.json"} {
		b, e := os.ReadFile(filepath.Join(root, name))
		if e != nil {
			return fail("BACKUP", "file")
		}
		if e = candidate.atomic(name, b); e != nil {
			return e
		}
	}
	if e = writeVolumeMap(&candidate, st); e != nil {
		return e
	}
	d.EnvPath = filepath.Join(candidateRoot, ".env")
	d.ComposePath = filepath.Join(candidateRoot, "compose.yaml")
	cc := NewController(&candidate, &d, c.clock)
	cc.WebCheck = c.WebCheck
	if e = cc.Start(ctx, nil); e != nil {
		_ = d.Stop(ctx, st)
		return e
	}
	_, ready, _ := candidate.Load()
	ready.Checkpoint = "restore-verified"
	if e = candidate.SaveState(ready); e != nil {
		return e
	}
	return fail("BACKUP", "restore-confirm")
}

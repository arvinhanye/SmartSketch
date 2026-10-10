package launch

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func TestUpgradeRequiresConfirmationAndVerifiedBackup(t *testing.T) {
	c, r := controllerFixture(t)
	target := manifestFixture()
	target.Version = "fixture-2"
	if _, e := c.PrepareUpgrade(context.Background(), target, false); e == nil {
		t.Fatal("unconfirmed upgrade")
	}
	if len(r.Requests) != 0 {
		t.Fatal("unconfirmed operation touched Docker")
	}
}
func TestRestoreRejectsTamperedOrForeignBackup(t *testing.T) {
	c, r := controllerFixture(t)
	set := BackupSet{ID: "0123456789abcdef", InstallID: "foreign"}
	if e := c.Restore(context.Background(), set, true); e == nil {
		t.Fatal("foreign restore")
	}
	if len(r.Requests) != 0 {
		t.Fatal("invalid backup touched Docker")
	}
}
func TestMissingRootKeyStopsRecovery(t *testing.T) {
	c, r := controllerFixture(t)
	removeConfig(t, c.store)
	if e := c.Restore(context.Background(), BackupSet{}, true); e == nil {
		t.Fatal("missing key ignored")
	}
	if len(r.Requests) != 0 {
		t.Fatal("missing key touched Docker")
	}
}

func removeConfig(t *testing.T, s *Store) {
	t.Helper()
	if e := os.Remove(filepath.Join(s.Root, ".env")); e != nil {
		t.Fatal(e)
	}
}

func TestVerifiedBackupRejectsChangedFileBeforeDocker(t *testing.T) {
	c, r := controllerFixture(t)
	cfg, st, _ := c.store.Load()
	st.Fresh = false
	st.Phase = STOPPED
	c.store.SaveState(st)
	id := "1111111111111111"
	root, _ := c.backupPath(id)
	bs := Store{Root: root}
	if e := bs.SaveConfig(cfg, st); e != nil {
		t.Fatal(e)
	}
	m := manifestFixture()
	compose := []byte("synthetic-compose")
	sum := sha256.Sum256(compose)
	m.ComposeSHA256 = hex.EncodeToString(sum[:])
	mb, _ := json.Marshal(m)
	bs.atomic("compose.yaml", compose)
	bs.atomic("release-manifest.json", mb)
	for _, name := range backupNames[4:] {
		bs.atomic(name, []byte("synthetic archive"))
	}
	set := BackupSet{ID: id, InstallID: st.InstallID, ReleaseVersion: m.Version, Files: map[string]string{}}
	for _, name := range backupNames {
		h, e := fileSHA(filepath.Join(root, name))
		if e != nil {
			t.Fatal(e)
		}
		set.Files[name] = h
	}
	set.ManifestSHA256 = set.Files["release-manifest.json"]
	if _, _, _, e := c.verifyBackup(set); e != nil {
		t.Fatal(e)
	}
	bs.atomic("neo4j.tar.gz", []byte("tampered"))
	if e := c.Restore(context.Background(), set, true); e == nil {
		t.Fatal("tampered restore")
	}
	if len(r.Requests) != 0 {
		t.Fatal("tampering touched Docker")
	}
	set.Files["../outside"] = "bad"
	if _, _, _, e := c.verifyBackup(set); e == nil {
		t.Fatal("unknown path accepted")
	}
}

func TestApplyUpgradeRejectsUnverifiedBackup(t *testing.T) {
	c, r := controllerFixture(t)
	if e := c.ApplyUpgrade(context.Background(), BackupSet{ID: "1111111111111111"}, true); e == nil {
		t.Fatal("unverified upgrade")
	}
	if len(r.Requests) != 0 {
		t.Fatal("unverified upgrade invoked Docker")
	}
}

// verifiedBackupFixture writes a verified backup of the stopped fixture install (release fixture-1) and returns
// it together with the target release (fixture-2) whose compose file the controller's Docker points at.
func verifiedBackupFixture(t *testing.T, c *Controller) (BackupSet, ReleaseManifest) {
	t.Helper()
	cfg, st, _ := c.store.Load()
	st.Fresh = false
	st.Phase = STOPPED
	if e := c.store.SaveState(st); e != nil {
		t.Fatal(e)
	}
	id := "2222222222222222"
	root, _ := c.backupPath(id)
	bs := Store{Root: root}
	if e := bs.SaveConfig(cfg, st); e != nil {
		t.Fatal(e)
	}
	old := manifestFixture()
	oldCompose := []byte("synthetic-compose-old")
	oldSum := sha256.Sum256(oldCompose)
	old.ComposeSHA256 = hex.EncodeToString(oldSum[:])
	ob, _ := json.Marshal(old)
	bs.atomic("compose.yaml", oldCompose)
	bs.atomic("release-manifest.json", ob)
	for _, name := range backupNames[4:] {
		bs.atomic(name, []byte("synthetic archive"))
	}
	set := BackupSet{ID: id, InstallID: st.InstallID, ReleaseVersion: old.Version, Files: map[string]string{}}
	for _, name := range backupNames {
		h, e := fileSHA(filepath.Join(root, name))
		if e != nil {
			t.Fatal(e)
		}
		set.Files[name] = h
	}
	set.ManifestSHA256 = set.Files["release-manifest.json"]
	target := manifestFixture()
	target.Version = "fixture-2"
	newCompose := []byte("synthetic-compose-new")
	newSum := sha256.Sum256(newCompose)
	target.ComposeSHA256 = hex.EncodeToString(newSum[:])
	c.docker.ComposePath = filepath.Join(t.TempDir(), "compose.yaml")
	if e := os.WriteFile(c.docker.ComposePath, newCompose, 0600); e != nil {
		t.Fatal(e)
	}
	c.docker.Manifest = target
	return set, target
}

func markPendingUpgrade(t *testing.T, c *Controller, id, target string) {
	t.Helper()
	b, _ := json.Marshal(map[string]string{"backup_id": id, "target_version": target})
	if e := c.store.atomic("upgrade.json", b); e != nil {
		t.Fatal(e)
	}
}

// Field report (rc-b59869d on a real preview install): after the backup step the installation is STOPPED with a pending
// upgrade, but any failed action (a click on "start", which the version guard rejects) persists Phase=ERROR, and the
// confirmation step then refused the same upgrade forever with "安装版本发生变化".
func TestApplyUpgradeStillWorksAfterAFailedActionLeftErrorPhase(t *testing.T) {
	c, _ := controllerFixture(t)
	set, target := verifiedBackupFixture(t, c)
	markPendingUpgrade(t, c, set.ID, target.Version)
	c.recordFailure(fail("VERSION", "upgrade")) // what the server does when "start" is refused
	if _, st, _ := c.store.Load(); st.Phase != ERROR {
		t.Fatalf("fixture must reproduce the ERROR phase, got %s", st.Phase)
	}
	_ = c.ApplyUpgrade(context.Background(), set, true) // may fail later while starting synthetic services
	_, st, e := c.store.Load()
	if e != nil {
		t.Fatal(e)
	}
	if st.ReleaseVersion != target.Version {
		t.Fatalf("upgrade was refused: still on %s", st.ReleaseVersion)
	}
}

func TestApplyUpgradeFromErrorPhaseRequiresTheMatchingPendingUpgrade(t *testing.T) {
	for name, pending := range map[string]func(*testing.T, *Controller, BackupSet, ReleaseManifest){
		"no pending record": func(*testing.T, *Controller, BackupSet, ReleaseManifest) {},
		"other backup": func(t *testing.T, c *Controller, _ BackupSet, m ReleaseManifest) {
			markPendingUpgrade(t, c, "3333333333333333", m.Version)
		},
		"other target": func(t *testing.T, c *Controller, s BackupSet, _ ReleaseManifest) {
			markPendingUpgrade(t, c, s.ID, "fixture-9")
		},
	} {
		t.Run(name, func(t *testing.T) {
			c, r := controllerFixture(t)
			set, target := verifiedBackupFixture(t, c)
			pending(t, c, set, target)
			c.recordFailure(fail("PROCESS", "control"))
			before := len(r.Requests)
			if e := c.ApplyUpgrade(context.Background(), set, true); e == nil {
				t.Fatal("upgrade from ERROR without a matching pending record was accepted")
			}
			if len(r.Requests) != before {
				t.Fatal("refused upgrade touched Docker")
			}
			if _, st, _ := c.store.Load(); st.ReleaseVersion == target.Version {
				t.Fatal("refused upgrade changed the release")
			}
		})
	}
}

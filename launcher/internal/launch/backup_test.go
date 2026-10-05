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

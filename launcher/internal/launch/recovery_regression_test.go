package launch

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func recoveryFixture(t *testing.T, checkpoint string) (*Controller, BackupSet, *Store, InstallState) {
	t.Helper()
	c, base := controllerFixture(t)
	c.docker.Runner = &restoreTransport{base: base}
	cfg, st, e := c.store.Load()
	if e != nil {
		t.Fatal(e)
	}
	st.Fresh = false
	st.Phase = STOPPED
	st.TeacherID = "fixture-id"
	c.store.SaveState(st)
	id := "1111111111111111"
	root, _ := c.backupPath(id)
	snapshot := Store{Root: root}
	snapshot.SaveConfig(cfg, st)
	m := manifestFixture()
	compose := []byte("synthetic-compose")
	sum := sha256.Sum256(compose)
	m.ComposeSHA256 = hex.EncodeToString(sum[:])
	b, _ := json.Marshal(m)
	snapshot.atomic("compose.yaml", compose)
	snapshot.atomic("release-manifest.json", b)
	for _, name := range backupNames[4:] {
		snapshot.atomic(name, []byte("synthetic archive"))
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
	candidate := &Store{Root: filepath.Join(c.store.Root, "candidates", id)}
	ready := st
	ready.DataGeneration = "2222222222222222"
	ready.Checkpoint = checkpoint
	candidate.SaveConfig(cfg, ready)
	candidate.atomic("compose.yaml", compose)
	candidate.atomic("release-manifest.json", b)
	writeVolumeMap(candidate, ready)
	return c, set, candidate, ready
}

type restoreTransport struct{ base *engineRunner }

func (r *restoreTransport) Run(ctx context.Context, q ProcessRequest) (ProcessResult, error) {
	if len(q.Args) > 1 && q.Args[0] == "volume" && q.Args[1] == "inspect" {
		return ProcessResult{Stdout: []byte(`{"com.docker.compose.project":"smartsketch-` + r.base.InstallID + `","io.smartsketch.installation":"` + r.base.InstallID + `"}`)}, nil
	}
	return r.base.Run(ctx, q)
}
func assertConfirmation(t *testing.T, e error) {
	t.Helper()
	f, ok := e.(*Failure)
	if !ok || f.Stage != "restore-confirm" {
		t.Fatalf("expected confirmation, got %v", e)
	}
}
func TestInterruptedCandidateCanResume(t *testing.T) {
	c, set, _, _ := recoveryFixture(t, "restore-staged")
	assertConfirmation(t, c.Restore(context.Background(), set, true))
	if e := c.Restore(context.Background(), set, true); e != nil {
		t.Fatal(e)
	}
}
func TestSameBackupSecondRestoreUsesFreshGeneration(t *testing.T) {
	c, set, _, ready := recoveryFixture(t, "restore-verified")
	if e := c.Restore(context.Background(), set, true); e != nil {
		t.Fatal(e)
	}
	assertConfirmation(t, c.Restore(context.Background(), set, true))
	_, st, _ := c.store.Load()
	if st.DataGeneration != ready.DataGeneration {
		t.Fatal("unconfirmed second restore switched active generation")
	}
	if e := c.Restore(context.Background(), set, true); e != nil {
		t.Fatal(e)
	}
	_, st, _ = c.store.Load()
	if st.DataGeneration == ready.DataGeneration {
		t.Fatal("reused live generation instead of snapshot")
	}
}

type activationFault struct {
	root  string
	fired bool
}

func (p *activationFault) SecureDir(path string) error {
	if path == p.root && !p.fired {
		b, _ := os.ReadFile(filepath.Join(p.root, "installation.json"))
		var st InstallState
		json.Unmarshal(b, &st)
		_, e := os.Stat(filepath.Join(p.root, "volumes.json"))
		if st.DataGeneration != "" && os.IsNotExist(e) || st.DataGeneration == "" && e == nil {
			p.fired = true
			return fmt.Errorf("synthetic interruption")
		}
	}
	return OSProtector{}.SecureDir(path)
}
func (p *activationFault) SecureFile(path string) error { return OSProtector{}.SecureFile(path) }
func TestRestoreActivationInterruptedGroupRecoversMapping(t *testing.T) {
	c, set, _, ready := recoveryFixture(t, "restore-verified")
	fault := &activationFault{root: c.store.Root}
	c.store.Permissions = fault
	if c.Restore(context.Background(), set, true) == nil || !fault.fired {
		t.Fatal("activation fault not exercised")
	}
	c.store.Permissions = OSProtector{}
	_, st, e := c.store.Load()
	if e != nil {
		t.Fatal(e)
	}
	b, e := os.ReadFile(filepath.Join(c.store.Root, "volumes.json"))
	if e != nil || st.DataGeneration != ready.DataGeneration || !strings.Contains(string(b), ready.DataGeneration) {
		t.Fatal("state published without volume mapping")
	}
}

package launch

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func setupFixture() SetupInput {
	return SetupInput{Embedding: EmbeddingConfig{BaseURL: "https://example.com/v1", Model: "fixture-embed", APIKey: NewSecret("fixture-key-unique"), Dimensions: 1024}, TeacherUsername: "teacher_one", TeacherPassword: NewSecret("fixture-pass-one"), ConfirmPassword: NewSecret("fixture-pass-one"), WebPort: 8080}
}
func configFixture(t *testing.T) Config {
	t.Helper()
	c, e := NewConfig(setupFixture(), bytes.NewReader(bytes.Repeat([]byte{7}, 256)))
	if e != nil {
		t.Fatal(e)
	}
	return c
}
func TestSecretHasNoPlaintextRepresentation(t *testing.T) {
	s := NewSecret("fixture-key-unique")
	if strings.Contains(fmt.Sprintf("%v %#v", s, s), "fixture-key-unique") {
		t.Fatal("leaked")
	}
	b, _ := json.Marshal(s)
	if bytes.Contains(b, []byte("fixture-key-unique")) {
		t.Fatal("JSON leaked")
	}
}
func TestEnvRoundTripSpecialCharacters(t *testing.T) {
	for _, v := range []string{"key $ # ' \" \\ inside", "ends\\", "apostrophe\\'", "unicode-测试"} {
		c := configFixture(t)
		c.Embedding.APIKey = NewSecret(v)
		b, e := EncodeEnv(c)
		if e != nil {
			t.Fatal(e)
		}
		got, e := DecodeEnv(b)
		if e != nil {
			t.Fatal(e)
		}
		if got.Embedding.APIKey.value != v || got.ModelCredentialKey.value != c.ModelCredentialKey.value {
			t.Fatal("bytes changed")
		}
	}
}
func TestEnvRejectsDuplicateAndMultiline(t *testing.T) {
	c := configFixture(t)
	b, _ := EncodeEnv(c)
	for _, extra := range []string{"EMBEDDING_MODEL='bad'\n", "UNKNOWN='x'\n", "BROKEN\n"} {
		if _, e := DecodeEnv(append(append([]byte{}, b...), []byte(extra)...)); e == nil {
			t.Fatal("accepted ambiguous config")
		}
	}
	for _, v := range []string{"abc\nX=evil", "abc\x00"} {
		c.Embedding.APIKey = NewSecret(v)
		if _, e := EncodeEnv(c); e == nil {
			t.Fatal("accepted injection")
		}
	}
	if _, e := DecodeEnv(bytes.ReplaceAll(b, []byte("\n"), []byte("\r\n"))); e != nil {
		t.Fatal("normal CRLF rejected", e)
	}
}
func TestSetupRejectsBadFields(t *testing.T) {
	for _, u := range []string{"http://example.com", "https://127.0.0.1", "https://user:pw@example.com", "https://example.com?key=x", "https://example.com#x", "https://localhost", "https://10.0.0.1"} {
		in := setupFixture()
		in.Embedding.BaseURL = u
		if ValidateSetup(in) == nil {
			t.Fatal("URL accepted", u)
		}
	}
	in := setupFixture()
	in.ConfirmPassword = NewSecret("different-password")
	if ValidateSetup(in) == nil {
		t.Fatal("mismatch accepted")
	}
	in = setupFixture()
	in.Embedding.Dimensions = 0
	if ValidateSetup(in) == nil {
		t.Fatal("bad dimensions")
	}
	in = setupFixture()
	in.TeacherUsername = "teacher/evil"
	if ValidateSetup(in) == nil {
		t.Fatal("bad username")
	}
	in = setupFixture()
	in.Embedding.APIKey = NewSecret("")
	if ValidateSetup(in) == nil {
		t.Fatal("blank API key")
	}
}

type deniedPermissions struct{}

func (deniedPermissions) SecureDir(string) error  { return fmt.Errorf("denied") }
func (deniedPermissions) SecureFile(string) error { return fmt.Errorf("denied") }
func TestStoreAtomicFailurePreservesExisting(t *testing.T) {
	s := Store{Root: filepath.Join(t.TempDir(), "私有 config")}
	c := configFixture(t)
	st := InstallState{SchemaVersion: 1, InstallID: "0123456789abcdef", Phase: CONFIGURED, WebPort: 8080, Fresh: true}
	if e := s.SaveConfig(c, st); e != nil {
		t.Fatal(e)
	}
	before, _ := os.ReadFile(filepath.Join(s.Root, ".env"))
	s.Permissions = deniedPermissions{}
	c.Embedding.APIKey = NewSecret("changed")
	if s.SaveConfig(c, st) == nil {
		t.Fatal("permission failure ignored")
	}
	after, _ := os.ReadFile(filepath.Join(s.Root, ".env"))
	if !bytes.Equal(before, after) {
		t.Fatal("old config lost")
	}
}
func TestMissingConfigDoesNotRekey(t *testing.T) {
	s := Store{Root: t.TempDir()}
	st := InstallState{SchemaVersion: 1, InstallID: "0123456789abcdef", Phase: CONFIGURED, WebPort: 8080, Fresh: true}
	if e := s.SaveState(st); e != nil {
		t.Fatal(e)
	}
	if _, _, e := s.Load(); e == nil {
		t.Fatal("missing env silently accepted")
	}
	if _, e := os.Stat(filepath.Join(s.Root, ".env")); !os.IsNotExist(e) {
		t.Fatal("env recreated")
	}
}
func TestInstanceLockConcurrentOpen(t *testing.T) {
	root := t.TempDir()
	a, e := AcquireInstance(root)
	if e != nil {
		t.Fatal(e)
	}
	if b, e := AcquireInstance(root); e == nil {
		b.Close()
		t.Fatal("two locks")
	}
	a.Close()
	b, e := AcquireInstance(root)
	if e != nil {
		t.Fatal(e)
	}
	b.Close()
}
func TestStoreRejectsSymlink(t *testing.T) {
	parent := t.TempDir()
	target := t.TempDir()
	link := filepath.Join(parent, "redirect")
	if e := os.Symlink(target, link); e != nil {
		t.Skip("OS denies symlink")
	}
	s := Store{Root: link}
	if e := s.SaveConfig(configFixture(t), InstallState{SchemaVersion: 1, InstallID: "0123456789abcdef", Phase: CONFIGURED, WebPort: 8080}); e == nil {
		t.Fatal("symlink accepted")
	}
}

type failAfterEnv struct {
	root  string
	fired bool
}

func (p *failAfterEnv) SecureDir(path string) error {
	b, _ := os.ReadFile(filepath.Join(p.root, ".env"))
	if path == p.root && !p.fired && strings.Contains(string(b), `WEB_PUBLISH_PORT="9000"`) {
		p.fired = true
		return fmt.Errorf("synthetic interruption")
	}
	return OSProtector{}.SecureDir(path)
}
func (p *failAfterEnv) SecureFile(path string) error { return OSProtector{}.SecureFile(path) }
func TestConfigurationInterruptedPairRecoversWithoutRekey(t *testing.T) {
	s := Store{Root: t.TempDir()}
	cfg := configFixture(t)
	st := InstallState{SchemaVersion: 1, InstallID: "0123456789abcdef", Phase: CONFIGURED, WebPort: 8080}
	if e := s.SaveConfig(cfg, st); e != nil {
		t.Fatal(e)
	}
	fault := &failAfterEnv{root: s.Root}
	s.Permissions = fault
	cfg.WebPort = 9000
	st.WebPort = 9000
	if s.SaveConfig(cfg, st) == nil || !fault.fired {
		t.Fatal("fault not exercised")
	}
	s.Permissions = OSProtector{}
	got, state, e := s.Load()
	if e != nil {
		t.Fatal("configuration not recoverable")
	}
	if got.WebPort != 9000 || state.WebPort != 9000 || got.ModelCredentialKey.value != cfg.ModelCredentialKey.value {
		t.Fatal("inconsistent/rekeyed recovery")
	}
}

func TestInitialConfigurationInterruptedAfterEnvRecoversIdentity(t *testing.T) {
	s := Store{Root: t.TempDir()}
	cfg := configFixture(t)
	cfg.WebPort = 9000
	st := InstallState{SchemaVersion: 1, InstallID: "0123456789abcdef", Phase: CONFIGURED, WebPort: 9000, Fresh: true}
	fault := &failAfterEnv{root: s.Root}
	s.Permissions = fault
	if s.SaveConfig(cfg, st) == nil || !fault.fired {
		t.Fatal("initial interruption not exercised")
	}
	s.Permissions = OSProtector{}
	got, state, e := s.Load()
	if e != nil || state.InstallID != st.InstallID || got.Neo4jPassword.value != cfg.Neo4jPassword.value || got.JWTSecret.value != cfg.JWTSecret.value || got.ModelCredentialKey.value != cfg.ModelCredentialKey.value {
		t.Fatal("initial configuration not recovered intact")
	}
}

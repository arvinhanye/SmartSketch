package launch

import (
	"encoding/json"
	"os"
	"path/filepath"
)

type Protector interface {
	SecureDir(string) error
	SecureFile(string) error
}
type Store struct {
	Root        string
	Permissions Protector
}

func noLinks(p string) error {
	p, e := filepath.Abs(p)
	if e != nil {
		return fail("PERMISSION", "path")
	}
	for {
		st, e := os.Lstat(p)
		if e == nil && st.Mode()&os.ModeSymlink != 0 {
			return fail("PERMISSION", "path")
		}
		if e != nil && !os.IsNotExist(e) {
			return fail("PERMISSION", "path")
		}
		next := filepath.Dir(p)
		if next == p {
			break
		}
		p = next
	}
	return nil
}
func (s *Store) ensure() error {
	if e := noLinks(s.Root); e != nil {
		return e
	}
	if e := os.MkdirAll(s.Root, 0700); e != nil {
		return fail("PERMISSION", "mkdir")
	}
	if s.Permissions == nil {
		s.Permissions = OSProtector{}
	}
	if s.Permissions.SecureDir(s.Root) != nil {
		return fail("PERMISSION", "directory")
	}
	return nil
}
func (s *Store) atomic(name string, b []byte) error {
	if e := s.ensure(); e != nil {
		return e
	}
	dest := filepath.Join(s.Root, name)
	if e := noLinks(dest); e != nil {
		return e
	}
	f, e := os.CreateTemp(s.Root, ".write-")
	if e != nil {
		return fail("PERMISSION", "write")
	}
	tmp := f.Name()
	defer os.Remove(tmp)
	defer f.Close()
	if s.Permissions.SecureFile(tmp) != nil {
		return fail("PERMISSION", "file")
	}
	if _, e = f.Write(b); e != nil {
		return fail("PERMISSION", "write")
	}
	if f.Sync() != nil || f.Close() != nil {
		return fail("PERMISSION", "sync")
	}
	if os.Rename(tmp, dest) != nil {
		return fail("PERMISSION", "replace")
	}
	return nil
}
func validState(st InstallState) bool {
	if st.SchemaVersion != 1 || !idPattern.MatchString(st.InstallID) || st.WebPort < 1024 || st.WebPort > 65535 {
		return false
	}
	switch st.Phase {
	case CONFIGURED, INITIALIZING, READY, STOPPED, ERROR:
		return true
	}
	return false
}
func (s *Store) SaveState(st InstallState) error {
	if !validState(st) {
		return fail("CONFIG", "state")
	}
	b, e := json.Marshal(st)
	if e != nil {
		return fail("CONFIG", "state")
	}
	return s.atomic("installation.json", b)
}
func (s *Store) SaveConfig(c Config, st InstallState) error {
	if !validState(st) || st.WebPort != c.WebPort {
		return fail("CONFIG", "state")
	}
	if e := s.ensure(); e != nil {
		return e
	}
	old, e := os.ReadFile(filepath.Join(s.Root, "installation.json"))
	if e == nil {
		var prev InstallState
		if strictJSON(old, &prev) != nil || prev.InstallID != st.InstallID {
			return fail("OWNERSHIP", "config")
		}
	} else if !os.IsNotExist(e) {
		return fail("CONFIG", "state")
	}
	b, e := EncodeEnv(c)
	if e != nil {
		return e
	}
	if _, e = DecodeEnv(b); e != nil {
		return e
	}
	if e = s.atomic(".env", b); e != nil {
		return e
	}
	return s.SaveState(st)
}
func (s *Store) Load() (Config, InstallState, error) {
	if e := noLinks(s.Root); e != nil {
		return Config{}, InstallState{}, e
	}
	b, e := os.ReadFile(filepath.Join(s.Root, "installation.json"))
	if os.IsNotExist(e) {
		if _, e := os.Stat(filepath.Join(s.Root, ".env")); !os.IsNotExist(e) {
			return Config{}, InstallState{}, fail("CONFIG", "recovery")
		}
		return Config{}, InstallState{Phase: NEW}, nil
	}
	if e != nil {
		return Config{}, InstallState{}, fail("CONFIG", "state")
	}
	var st InstallState
	if strictJSON(b, &st) != nil || !validState(st) {
		return Config{}, InstallState{}, fail("CONFIG", "state")
	}
	if e := noLinks(filepath.Join(s.Root, ".env")); e != nil {
		return Config{}, st, e
	}
	b, e = os.ReadFile(filepath.Join(s.Root, ".env"))
	if e != nil {
		return Config{}, st, fail("CONFIG", "recovery")
	}
	c, e := DecodeEnv(b)
	if e != nil || c.WebPort != st.WebPort {
		return Config{}, st, fail("CONFIG", "decode")
	}
	return c, st, nil
}

package launch

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"os"
	"path/filepath"
)

// A private write-ahead journal makes a config/release group recoverable after
// interruption. Only fixed launcher-owned files are admitted. Readers recover
// the complete group before using any member; no new keys are generated.
type fileTransaction struct {
	ID       string
	New      map[string]string
	Previous map[string]string
}

var transactionOrder = []string{".env", "compose.yaml", "release-manifest.json", "volumes.json", "installation.json"}

func transactionNameAllowed(name string) bool {
	for _, n := range transactionOrder {
		if n == name {
			return true
		}
	}
	return false
}
func fileContent(s *Store, name string) ([]byte, error) {
	p := filepath.Join(s.Root, name)
	if noLinks(p) != nil {
		return nil, fail("PERMISSION", "path")
	}
	b, e := os.ReadFile(p)
	if e != nil {
		return nil, fail("CONFIG", "transaction")
	}
	return b, nil
}
func validateFileGroup(files map[string][]byte) error {
	var st InstallState
	if strictJSON(files["installation.json"], &st) != nil || !validState(st) {
		return fail("CONFIG", "transaction-state")
	}
	cfg, e := DecodeEnv(files[".env"])
	if e != nil || cfg.WebPort != st.WebPort {
		return fail("CONFIG", "transaction-config")
	}
	if b, ok := files["volumes.json"]; ok {
		expected, e := volumeMapBytes(st)
		if e != nil || string(b) != string(expected) {
			return fail("CONFIG", "transaction-volumes")
		}
	}
	if manifest, ok := files["release-manifest.json"]; ok {
		var m ReleaseManifest
		if strictJSON(manifest, &m) != nil || m.Version != st.ReleaseVersion {
			return fail("MANIFEST", "transaction")
		}
		if compose, ok := files["compose.yaml"]; ok {
			if hashBytes(compose) != m.ComposeSHA256 {
				return fail("MANIFEST", "transaction")
			}
		} else {
			return fail("MANIFEST", "transaction")
		}
	}
	return nil
}
func (s *Store) commitGroup(files map[string][]byte) error {
	if e := s.recoverGroup(); e != nil {
		return e
	}
	if e := s.ensure(); e != nil {
		return e
	}
	for name := range files {
		if !transactionNameAllowed(name) {
			return fail("CONFIG", "transaction-file")
		}
	}
	for _, name := range []string{".env", "installation.json"} {
		if _, ok := files[name]; !ok {
			b, e := fileContent(s, name)
			if e != nil {
				return e
			}
			files[name] = b
		}
	}
	if e := validateFileGroup(files); e != nil {
		return e
	}
	if e := noLinks(filepath.Join(s.Root, "installation.json")); e != nil {
		return e
	}
	if old, e := os.ReadFile(filepath.Join(s.Root, "installation.json")); e == nil {
		var previous, next InstallState
		if strictJSON(old, &previous) != nil || strictJSON(files["installation.json"], &next) != nil || previous.InstallID != next.InstallID {
			return fail("OWNERSHIP", "transaction")
		}
		b, e := fileContent(s, ".env")
		if e != nil {
			return e
		}
		oldCfg, e := DecodeEnv(b)
		newCfg, newErr := DecodeEnv(files[".env"])
		if e != nil || newErr != nil || oldCfg.ModelCredentialKey.value != newCfg.ModelCredentialKey.value || oldCfg.Neo4jPassword.value != newCfg.Neo4jPassword.value || oldCfg.JWTSecret.value != newCfg.JWTSecret.value {
			return fail("CONFIG", "key-preservation")
		}
	}
	id, e := newID()
	if e != nil {
		return e
	}
	staging := Store{Root: filepath.Join(s.Root, "transactions", id), Permissions: s.Permissions}
	tx := fileTransaction{ID: id, New: map[string]string{}, Previous: map[string]string{}}
	for _, name := range transactionOrder {
		body, ok := files[name]
		if !ok {
			continue
		}
		if e = staging.atomic(name, body); e != nil {
			return e
		}
		tx.New[name] = hashBytes(body)
		p := filepath.Join(s.Root, name)
		if noLinks(p) != nil {
			return fail("PERMISSION", "path")
		}
		old, e := os.ReadFile(p)
		if e == nil {
			tx.Previous[name] = hashBytes(old)
		} else if os.IsNotExist(e) {
			tx.Previous[name] = ""
		} else {
			return fail("CONFIG", "transaction")
		}
	}
	b, _ := json.Marshal(tx)
	if e = s.atomic(".transaction.json", b); e != nil {
		return e
	}
	return s.recoverGroup()
}
func (s *Store) recoverGroup() error {
	marker := filepath.Join(s.Root, ".transaction.json")
	if noLinks(marker) != nil {
		return fail("PERMISSION", "path")
	}
	b, e := os.ReadFile(marker)
	if os.IsNotExist(e) {
		return nil
	}
	if e != nil || len(b) > 16384 {
		return fail("CONFIG", "transaction")
	}
	var tx fileTransaction
	if strictJSON(b, &tx) != nil || !idPattern.MatchString(tx.ID) || len(tx.New) < 2 || len(tx.New) != len(tx.Previous) {
		return fail("CONFIG", "transaction")
	}
	staging := Store{Root: filepath.Join(s.Root, "transactions", tx.ID), Permissions: s.Permissions}
	files := map[string][]byte{}
	for name, newHash := range tx.New {
		if !transactionNameAllowed(name) || !digest.MatchString(newHash) {
			return fail("CONFIG", "transaction")
		}
		oldHash, ok := tx.Previous[name]
		if !ok || (oldHash != "" && !digest.MatchString(oldHash)) {
			return fail("CONFIG", "transaction")
		}
		body, e := fileContent(&staging, name)
		if e != nil || hashBytes(body) != newHash {
			return fail("CONFIG", "transaction-checksum")
		}
		files[name] = body
		p := filepath.Join(s.Root, name)
		if noLinks(p) != nil {
			return fail("PERMISSION", "path")
		}
		current, e := os.ReadFile(p)
		if e == nil {
			hash := hashBytes(current)
			if hash != oldHash && hash != newHash {
				return fail("CONFIG", "transaction-conflict")
			}
		} else if !os.IsNotExist(e) || oldHash != "" {
			return fail("CONFIG", "transaction-conflict")
		}
	}
	if e = validateFileGroup(files); e != nil {
		return e
	}
	for _, name := range transactionOrder {
		if body, ok := files[name]; ok {
			if e = s.atomic(name, body); e != nil {
				return e
			}
		}
	}
	if e = os.Remove(marker); e != nil {
		return fail("CONFIG", "transaction-finish")
	}
	return nil
}

func hashBytes(b []byte) string { h := sha256.Sum256(b); return hex.EncodeToString(h[:]) }

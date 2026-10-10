package launch

import (
	"crypto/sha256"
	"fmt"
	"os"
	"regexp"
)

type ReleaseManifest struct {
	Version       string   `json:"version"`
	BackendImage  string   `json:"backend_image"`
	FrontendImage string   `json:"frontend_image"`
	Neo4jImage    string   `json:"neo4j_image"`
	ComposeSHA256 string   `json:"compose_sha256"`
	Targets       []string `json:"targets"`
}

var digest = regexp.MustCompile(`^[a-f0-9]{64}$`)
var versionPattern = regexp.MustCompile(`^[a-zA-Z0-9._-]{1,64}$`)

func LoadManifest(path string) (ReleaseManifest, error) {
	b, e := os.ReadFile(path)
	if e != nil {
		return ReleaseManifest{}, fail("MANIFEST", "read")
	}
	var m ReleaseManifest
	if strictJSON(b, &m) != nil || !versionPattern.MatchString(m.Version) || !digest.MatchString(m.ComposeSHA256) {
		return m, fail("MANIFEST", "parse")
	}
	for _, v := range []struct{ s, p string }{{m.BackendImage, "ghcr.io/arvinhanye/smartsketch-backend@sha256:"}, {m.FrontendImage, "ghcr.io/arvinhanye/smartsketch-frontend@sha256:"}, {m.Neo4jImage, "neo4j@sha256:"}} {
		if len(v.s) != len(v.p)+64 || v.s[:len(v.p)] != v.p || !digest.MatchString(v.s[len(v.p):]) {
			return m, fail("MANIFEST", "image")
		}
	}
	seen := map[string]bool{}
	for _, x := range m.Targets {
		if x != "darwin-arm64" && x != "darwin-amd64" && x != "windows-amd64" || seen[x] {
			return m, fail("MANIFEST", "targets")
		}
		seen[x] = true
	}
	if len(seen) != 3 {
		return m, fail("MANIFEST", "targets")
	}
	return m, nil
}
func (m ReleaseManifest) VerifyCompose(path string) error {
	b, e := os.ReadFile(path)
	if e != nil || fmt.Sprintf("%x", sha256.Sum256(b)) != m.ComposeSHA256 {
		return fail("MANIFEST", "compose")
	}
	return nil
}

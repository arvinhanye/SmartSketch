package launch

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"
)

type controlCapability struct {
	Origin string `json:"origin"`
	Key    string `json:"key"`
}

func (s *Store) SaveControl(origin string, secret Secret) error {
	if validateWebURL(origin) != nil {
		return fail("AUTH", "control")
	}
	b, _ := json.Marshal(controlCapability{origin, secret.value})
	return s.atomic("control.json", b)
}
func (s *Store) RemoveControl() { _ = os.Remove(filepath.Join(s.Root, "control.json")) }
func (s *Store) Reopen(ctx context.Context) error {
	path := filepath.Join(s.Root, "control.json")
	if noLinks(path) != nil {
		return fail("AUTH", "control")
	}
	b, e := os.ReadFile(path)
	if e != nil {
		return fail("LOCK", "control")
	}
	var cap controlCapability
	if strictJSON(b, &cap) != nil || validateWebURL(cap.Origin) != nil || len(cap.Key) != 64 {
		return fail("AUTH", "control")
	}
	req, e := http.NewRequestWithContext(ctx, "POST", cap.Origin+"/control/reopen", strings.NewReader("{}"))
	if e != nil {
		return fail("AUTH", "control")
	}
	req.Header.Set("Origin", cap.Origin)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+cap.Key)
	client := http.Client{Timeout: 3 * time.Second, CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }}
	r, e := client.Do(req)
	if e != nil {
		return fail("LOCK", "control")
	}
	defer r.Body.Close()
	b, e = io.ReadAll(io.LimitReader(r.Body, 4097))
	var value struct {
		Fragment string `json:"fragment"`
	}
	if e != nil || r.StatusCode != 200 || strictJSON(b, &value) != nil || !digest.MatchString(value.Fragment) {
		return fail("AUTH", "control")
	}
	return OpenBrowser(cap.Origin + "/#" + value.Fragment)
}

// Seed only release assets, never an existing installation's configuration or keys.
func (s *Store) SeedRelease(manifestPath, composePath string, m ReleaseManifest) error {
	_, st, e := s.Load()
	if e != nil {
		return e
	}
	if st.Phase != NEW {
		return nil
	}
	if m.VerifyCompose(composePath) != nil {
		return fail("MANIFEST", "compose")
	}
	for _, item := range []struct{ source, dest string }{{manifestPath, "release-manifest.json"}, {composePath, "compose.yaml"}} {
		b, e := os.ReadFile(item.source)
		if e != nil {
			return fail("MANIFEST", "read")
		}
		if e = s.atomic(item.dest, b); e != nil {
			return e
		}
	}
	return nil
}
func (c *Controller) Resume(ctx context.Context) {
	_, st, e := c.store.Load()
	if e != nil {
		c.recordFailure(e)
		return
	}
	if st.Phase != NEW && !st.Fresh {
		if e = c.Start(ctx, nil); e != nil {
			c.recordFailure(e)
		}
	}
}

func SessionFragment(s Secret) string { return s.value }

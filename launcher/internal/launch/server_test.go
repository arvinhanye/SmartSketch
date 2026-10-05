package launch

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func requestControl(h http.Handler, method, path, body, host, origin, token string) *httptest.ResponseRecorder {
	r := httptest.NewRequest(method, "http://127.0.0.1:8765"+path, strings.NewReader(body))
	r.Host = host
	r.Header.Set("Origin", origin)
	r.Header.Set("Content-Type", "application/json")
	if token != "" {
		r.Header.Set("Authorization", "Bearer "+token)
	}
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	return w
}
func exchange(t *testing.T, h http.Handler) string {
	t.Helper()
	w := requestControl(h, "POST", "/control/exchange", `{}`, "127.0.0.1:8765", "http://127.0.0.1:8765", "fixture-seed")
	if w.Code != 200 {
		t.Fatalf("exchange %d", w.Code)
	}
	var v struct {
		Token string `json:"token"`
	}
	json.Unmarshal(w.Body.Bytes(), &v)
	return v.Token
}
func TestControlRequiresTokenHostAndOrigin(t *testing.T) {
	c, _ := controllerFixture(t)
	h := NewServer(c, NewSecret("fixture-seed"), "http://127.0.0.1:8765")
	token := exchange(t, h)
	for _, row := range []struct{ method, host, origin, token string }{{"POST", "evil.test", "http://127.0.0.1:8765", token}, {"POST", "127.0.0.1:8765", "http://evil.test", token}, {"POST", "127.0.0.1:8765", "http://127.0.0.1:8765", ""}, {"GET", "127.0.0.1:8765", "", token}} {
		w := requestControl(h, row.method, "/control/stop", `{}`, row.host, row.origin, row.token)
		if w.Code < 400 {
			t.Fatal("invalid control accepted")
		}
	}
	if requestControl(h, "POST", "/control/exchange", `{}`, "127.0.0.1:8765", "http://127.0.0.1:8765", "fixture-seed").Code != 403 {
		t.Fatal("seed reused")
	}
}
func TestControlRejectsUnknownFieldsAndLargeBody(t *testing.T) {
	c, _ := controllerFixture(t)
	h := NewServer(c, NewSecret("fixture-seed"), "http://127.0.0.1:8765")
	token := exchange(t, h)
	for _, body := range []string{`{"path":"/tmp"}`, `{"confirmed":true,"confirmed":false}`, `{} {}`, strings.Repeat(" ", 16385)} {
		w := requestControl(h, "POST", "/control/stop", body, "127.0.0.1:8765", "http://127.0.0.1:8765", token)
		if w.Code != 400 {
			t.Fatalf("expected400 got%d", w.Code)
		}
	}
}
func TestDiagnosticsContainsNoSecretOrRawStderr(t *testing.T) {
	d := SanitizeDiagnostic("fixture-secret", "fixture-secret")
	b, _ := json.Marshal(d)
	if strings.Contains(string(b), "fixture-secret") {
		t.Fatal("unclassified text leaked")
	}
}

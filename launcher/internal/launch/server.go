package launch

import (
	"context"
	"crypto/rand"
	"crypto/subtle"
	"embed"
	"encoding/hex"
	"encoding/json"
	"io"
	"mime"
	"net/http"
	"net/url"
	"strings"
	"sync"
	"time"
)

//go:embed ui/*
var assets embed.FS

func NewSession() (Secret, error) {
	b := make([]byte, 32)
	if _, e := rand.Read(b); e != nil {
		return Secret{}, fail("AUTH", "random")
	}
	return NewSecret(hex.EncodeToString(b)), nil
}

type controlServer struct {
	controller          *Controller
	host, origin        string
	master, seed, token Secret
	expires             time.Time
	mu                  sync.Mutex
	busy                bool
}

func NewServer(c *Controller, session Secret, origin string) http.Handler {
	u, _ := url.Parse(origin)
	return &controlServer{controller: c, host: u.Host, origin: origin, master: session, seed: session, expires: time.Now().Add(20 * time.Minute)}
}
func equalToken(a, b string) bool {
	return a != "" && b != "" && subtle.ConstantTimeCompare([]byte(a), []byte(b)) == 1
}
func (s *controlServer) write(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}
func (s *controlServer) bad(w http.ResponseWriter, status int, code string) {
	s.write(w, status, fail(code, "control"))
}
func (s *controlServer) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Cache-Control", "no-store")
	w.Header().Set("X-Content-Type-Options", "nosniff")
	w.Header().Set("Referrer-Policy", "no-referrer")
	w.Header().Set("Content-Security-Policy", "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
	if r.Host != s.host {
		s.bad(w, 403, "AUTH")
		return
	}
	if !strings.HasPrefix(r.URL.Path, "/control/") {
		if r.Method != "GET" {
			s.bad(w, 405, "AUTH")
			return
		}
		name := map[string]string{"/": "ui/index.html", "/app.js": "ui/app.js", "/style.css": "ui/style.css"}[r.URL.Path]
		if name == "" {
			http.NotFound(w, r)
			return
		}
		b, e := assets.ReadFile(name)
		if e != nil {
			http.NotFound(w, r)
			return
		}
		ct := map[string]string{"/": "text/html; charset=utf-8", "/app.js": "text/javascript; charset=utf-8", "/style.css": "text/css; charset=utf-8"}[r.URL.Path]
		w.Header().Set("Content-Type", ct)
		_, _ = w.Write(b)
		return
	}
	isStatus := r.URL.Path == "/control/status"
	if (isStatus && r.Method != "GET") || (!isStatus && r.Method != "POST") {
		s.bad(w, 405, "AUTH")
		return
	}
	media, _, _ := mime.ParseMediaType(r.Header.Get("Content-Type"))
	if r.Method == "POST" && (r.Header.Get("Origin") != s.origin || media != "application/json") {
		s.bad(w, 403, "AUTH")
		return
	}
	token := ""
	if strings.HasPrefix(r.Header.Get("Authorization"), "Bearer ") {
		token = strings.TrimPrefix(r.Header.Get("Authorization"), "Bearer ")
	}
	s.mu.Lock()
	authenticated := equalToken(token, s.token.value) && time.Now().Before(s.expires)
	seedOK := equalToken(token, s.seed.value) && time.Now().Before(s.expires)
	masterOK := equalToken(token, s.master.value)
	s.mu.Unlock()
	path := r.URL.Path
	if path == "/control/exchange" {
		if !seedOK {
			s.bad(w, 403, "AUTH")
			return
		}
		var body struct{}
		if readBody(r, &body) != nil {
			s.bad(w, 400, "FIELD")
			return
		}
		next, e := NewSession()
		if e != nil {
			s.bad(w, 500, "AUTH")
			return
		}
		s.mu.Lock()
		if !equalToken(token, s.seed.value) {
			s.mu.Unlock()
			s.bad(w, 403, "AUTH")
			return
		}
		s.seed = Secret{}
		s.token = next
		s.expires = time.Now().Add(2 * time.Hour)
		s.mu.Unlock()
		s.write(w, 200, map[string]string{"token": next.value})
		return
	}
	// Reopening uses a protected per-process control capability, never a page cookie.
	if path == "/control/reopen" {
		if !masterOK {
			s.bad(w, 403, "AUTH")
			return
		}
		var body struct{}
		if readBody(r, &body) != nil {
			s.bad(w, 400, "FIELD")
			return
		}
		next, e := NewSession()
		if e != nil {
			s.bad(w, 500, "AUTH")
			return
		}
		s.mu.Lock()
		s.seed = next
		s.expires = time.Now().Add(20 * time.Minute)
		s.mu.Unlock()
		s.write(w, 200, map[string]string{"fragment": next.value})
		return
	}
	if !authenticated {
		s.bad(w, 403, "AUTH")
		return
	}
	if isStatus {
		v, e := s.controller.Status(r.Context())
		s.mu.Lock()
		v.Busy = v.Busy || s.busy
		s.mu.Unlock()
		if e != nil {
			s.bad(w, 409, "CONFIG")
			return
		}
		s.write(w, 200, v)
		return
	}
	var input SetupInput
	switch path {
	case "/control/setup":
		if readBody(r, &input) != nil {
			s.bad(w, 400, "FIELD")
			return
		}
		if ValidateSetup(input) != nil {
			s.bad(w, 400, "FIELD")
			return
		}
	case "/control/start":
		var data struct {
			Username string `json:"teacher_username"`
			Password Secret `json:"teacher_password"`
			Confirm  Secret `json:"confirm_password"`
		}
		if readBody(r, &data) != nil {
			s.bad(w, 400, "FIELD")
			return
		}
		cfg, st, e := s.controller.store.Load()
		if e != nil {
			s.bad(w, 409, "CONFIG")
			return
		}
		input = SetupInput{Embedding: cfg.Embedding, WebPort: cfg.WebPort, TeacherUsername: data.Username, TeacherPassword: data.Password, ConfirmPassword: data.Confirm}
		if st.Fresh && st.TeacherID == "" && ValidateSetup(input) != nil {
			s.bad(w, 400, "FIELD")
			return
		}
	case "/control/stop", "/control/open", "/control/diagnostics":
		var empty struct{}
		if readBody(r, &empty) != nil {
			s.bad(w, 400, "FIELD")
			return
		}
	default:
		http.NotFound(w, r)
		return
	}
	if path == "/control/diagnostics" {
		v, _ := s.controller.Status(r.Context())
		code := "PROCESS"
		if v.Failure != nil {
			code = v.Failure.Code
		}
		s.write(w, 200, SanitizeDiagnostic(v.Stage, code))
		return
	}
	if path == "/control/open" {
		v, e := s.controller.Status(r.Context())
		if e != nil || v.Phase != READY || validateWebURL(v.WebURL) != nil {
			s.bad(w, 409, "HEALTH")
			return
		}
		if OpenBrowser(v.WebURL) != nil {
			s.bad(w, 500, "PROCESS")
			return
		}
		s.write(w, 200, map[string]bool{"opened": true})
		return
	}
	s.mu.Lock()
	if s.busy {
		s.mu.Unlock()
		s.bad(w, 409, "LOCK")
		return
	}
	s.busy = true
	s.mu.Unlock()
	if path == "/control/setup" {
		if e := s.controller.Configure(input); e != nil {
			s.mu.Lock()
			s.busy = false
			s.mu.Unlock()
			s.bad(w, 409, "CONFIG")
			return
		}
	}
	go func() {
		defer func() { input = SetupInput{}; s.mu.Lock(); s.busy = false; s.mu.Unlock() }()
		ctx := context.Background()
		if path == "/control/stop" {
			if e := s.controller.Stop(ctx); e != nil {
				s.controller.recordFailure(e)
			}
		} else {
			if e := s.controller.Start(ctx, &input); e != nil {
				s.controller.recordFailure(e)
			}
		}
	}()
	s.write(w, 202, map[string]bool{"accepted": true})
}
func readBody(r *http.Request, out any) error {
	b, e := io.ReadAll(io.LimitReader(r.Body, 16385))
	if e != nil || len(b) > 16384 {
		return fail("FIELD", "input")
	}
	return strictJSON(b, out)
}

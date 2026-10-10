package launch

import (
	"context"
	"net"
	"net/http"
	"net/url"
	"time"
)

type Clock interface {
	Now() time.Time
	Sleep(context.Context, time.Duration) error
}
type wallClock struct{}

func (wallClock) Now() time.Time { return time.Now() }
func (wallClock) Sleep(ctx context.Context, d time.Duration) error {
	t := time.NewTimer(d)
	defer t.Stop()
	select {
	case <-ctx.Done():
		return ctx.Err()
	case <-t.C:
		return nil
	}
}

type SnapshotReader func(context.Context) (Snapshot, error)

func isReady(s Snapshot) bool {
	return s.ProjectOwned && s.Neo4jHealthy && s.APIHealthy && s.WorkerHealthy && s.WebHealthy && s.SchemaCurrent && s.EmbeddingSpaceMatches && s.VectorIndexesOnline
}
func WaitReady(ctx context.Context, read SnapshotReader, clock Clock, limit time.Duration) error {
	if clock == nil {
		clock = wallClock{}
	}
	deadline := clock.Now().Add(limit)
	for {
		if ctx.Err() != nil {
			return fail("HEALTH", "cancelled")
		}
		if !clock.Now().Before(deadline) {
			return fail("HEALTH", "deadline")
		}
		s, e := read(ctx)
		if e == nil && isReady(s) {
			return nil
		}
		if f, ok := e.(*Failure); ok && f.Code == "OWNERSHIP" {
			return f
		}
		left := deadline.Sub(clock.Now())
		if left <= 0 {
			return fail("HEALTH", "deadline")
		}
		if left > time.Second {
			left = time.Second
		}
		if clock.Sleep(ctx, left) != nil {
			return fail("HEALTH", "cancelled")
		}
	}
}
func validateWebURL(raw string) error {
	u, e := url.Parse(raw)
	if e != nil || u.Scheme != "http" || u.Hostname() != "127.0.0.1" || u.Port() == "" || u.User != nil || u.RawQuery != "" || u.Fragment != "" || (u.Path != "" && u.Path != "/") {
		return fail("AUTH", "url")
	}
	return nil
}
func checkWeb(ctx context.Context, port int) error {
	client := &http.Client{Timeout: 3 * time.Second, CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }}
	req, e := http.NewRequestWithContext(ctx, "GET", webURL(port)+"/health", nil)
	if e != nil {
		return fail("HEALTH", "web")
	}
	r, e := client.Do(req)
	if e != nil {
		return fail("HEALTH", "web")
	}
	defer r.Body.Close()
	if r.StatusCode != 200 {
		return fail("HEALTH", "web")
	}
	return nil
}
func checkPort(port int) error {
	l, e := net.Listen("tcp4", net.JoinHostPort("127.0.0.1", portString(port)))
	if e != nil {
		return fail("PORT", "web")
	}
	return l.Close()
}

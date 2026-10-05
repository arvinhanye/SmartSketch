package launch

import (
	"encoding/base64"
	"fmt"
	"io"
	"net"
	"net/url"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"unicode/utf8"
)

var userPattern = regexp.MustCompile(`^[a-z0-9_.-]{3,32}$`)
var idPattern = regexp.MustCompile(`^[a-f0-9]{16}$`)

func validURL(raw string) bool {
	u, e := url.Parse(raw)
	if e != nil || u.Scheme != "https" || u.Hostname() == "" || u.User != nil || u.RawQuery != "" || u.Fragment != "" {
		return false
	}
	h := strings.ToLower(u.Hostname())
	if h == "localhost" || strings.HasSuffix(h, ".localhost") || strings.HasSuffix(h, ".local") {
		return false
	}
	if ip := net.ParseIP(h); ip != nil && (ip.IsPrivate() || ip.IsLoopback() || ip.IsUnspecified() || ip.IsLinkLocalUnicast() || ip.IsMulticast()) {
		return false
	}
	return true
}
func cleanValue(s string) bool { return !strings.ContainsAny(s, "\r\n\x00") && utf8.ValidString(s) }
func ValidateSetup(in SetupInput) error {
	n := utf8.RuneCountInString(in.TeacherPassword.value)
	if !validURL(in.Embedding.BaseURL) || !userPattern.MatchString(strings.ToLower(in.TeacherUsername)) || n < 8 || n > 128 || in.TeacherPassword.value != in.ConfirmPassword.value || in.Embedding.Dimensions < 1 || strings.TrimSpace(in.Embedding.Model) == "" || strings.TrimSpace(in.Embedding.APIKey.value) == "" || in.WebPort < 1024 || in.WebPort > 65535 {
		return fail("FIELD", "config")
	}
	for _, s := range []string{in.Embedding.BaseURL, in.Embedding.APIKey.value, in.Embedding.Model, in.TeacherPassword.value} {
		if !cleanValue(s) {
			return fail("FIELD", "config")
		}
	}
	return nil
}
func NewConfig(in SetupInput, r io.Reader) (Config, error) {
	if e := ValidateSetup(in); e != nil {
		return Config{}, e
	}
	gen := func(n int) (Secret, error) {
		b := make([]byte, n)
		if _, e := io.ReadFull(r, b); e != nil {
			return Secret{}, fail("CONFIG", "random")
		}
		return NewSecret(base64.URLEncoding.EncodeToString(b)), nil
	}
	root, e := gen(32)
	if e != nil {
		return Config{}, e
	}
	jwt, e := gen(48)
	if e != nil {
		return Config{}, e
	}
	neo, e := gen(24)
	if e != nil {
		return Config{}, e
	}
	return Config{in.Embedding, neo, jwt, root, in.WebPort}, nil
}
func configValues(c Config) map[string]string {
	return map[string]string{"APP_ENV": "production", "LLM_MODE": "personal", "EMBEDDING_MODE": "online", "EMBEDDING_BASE_URL": c.Embedding.BaseURL, "EMBEDDING_API_KEY": c.Embedding.APIKey.value, "EMBEDDING_MODEL": c.Embedding.Model, "EMBEDDING_DIMENSIONS": strconv.Itoa(c.Embedding.Dimensions), "NEO4J_USER": "neo4j", "NEO4J_PASSWORD": c.Neo4jPassword.value, "AUTH_JWT_SECRET": c.JWTSecret.value, "MODEL_CREDENTIAL_KEY": c.ModelCredentialKey.value, "WEB_PUBLISH_PORT": strconv.Itoa(c.WebPort)}
}
func EncodeEnv(c Config) ([]byte, error) {
	values := configValues(c)
	keys := []string{}
	for k, v := range values {
		if !cleanValue(v) {
			return nil, fail("CONFIG", "encode")
		}
		keys = append(keys, k)
	}
	sort.Strings(keys)
	var b strings.Builder
	for _, k := range keys {
		v := strconv.Quote(strings.ReplaceAll(values[k], "$", "$$"))
		fmt.Fprintf(&b, "%s=%s\n", k, v)
	}
	return []byte(b.String()), nil
}
func DecodeEnv(b []byte) (Config, error) {
	m := map[string]string{}
	allowed := configValues(Config{})
	for _, line := range strings.Split(strings.ReplaceAll(string(b), "\r\n", "\n"), "\n") {
		if line == "" {
			continue
		}
		k, v, ok := strings.Cut(line, "=")
		if !ok {
			return Config{}, fail("CONFIG", "decode")
		}
		if _, ok := allowed[k]; !ok {
			return Config{}, fail("CONFIG", "decode")
		}
		if _, ok := m[k]; ok {
			return Config{}, fail("CONFIG", "decode")
		}
		v, e := strconv.Unquote(v)
		if e != nil || !cleanValue(v) {
			return Config{}, fail("CONFIG", "decode")
		}
		m[k] = strings.ReplaceAll(v, "$$", "$")
	}
	if len(m) != len(allowed) || m["APP_ENV"] != "production" || m["LLM_MODE"] != "personal" || m["EMBEDDING_MODE"] != "online" || m["NEO4J_USER"] != "neo4j" {
		return Config{}, fail("CONFIG", "decode")
	}
	dim, e := strconv.Atoi(m["EMBEDDING_DIMENSIONS"])
	if e != nil {
		return Config{}, fail("CONFIG", "decode")
	}
	port, e := strconv.Atoi(m["WEB_PUBLISH_PORT"])
	if e != nil {
		return Config{}, fail("CONFIG", "decode")
	}
	c := Config{EmbeddingConfig{m["EMBEDDING_BASE_URL"], m["EMBEDDING_MODEL"], NewSecret(m["EMBEDDING_API_KEY"]), dim}, NewSecret(m["NEO4J_PASSWORD"]), NewSecret(m["AUTH_JWT_SECRET"]), NewSecret(m["MODEL_CREDENTIAL_KEY"]), port}
	probe := SetupInput{c.Embedding, "validation", NewSecret("temporary-validation"), NewSecret("temporary-validation"), port}
	if ValidateSetup(probe) != nil || len(c.JWTSecret.value) < 32 || len(c.Neo4jPassword.value) < 8 {
		return Config{}, fail("CONFIG", "decode")
	}
	key, e := base64.URLEncoding.DecodeString(c.ModelCredentialKey.value)
	if e != nil || len(key) != 32 {
		return Config{}, fail("CONFIG", "decode")
	}
	return c, nil
}

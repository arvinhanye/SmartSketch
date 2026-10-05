package launch

import "runtime"

var Version = "development"

type Diagnostic struct {
	Version  string   `json:"version"`
	Platform string   `json:"platform"`
	Stage    string   `json:"stage"`
	Failure  *Failure `json:"failure"`
}

func SanitizeDiagnostic(stage, code string) Diagnostic {
	stages := map[string]bool{"environment": true, "pull": true, "neo4j": true, "migrate": true, "teacher": true, "app": true, "readiness": true, "stopping": true, "upgrade": true, "backup": true, "restore": true}
	if !stages[stage] {
		stage = "unknown"
	}
	codes := map[string]bool{"FIELD": true, "CONFIG": true, "PERMISSION": true, "LOCK": true, "DOCKER": true, "OWNERSHIP": true, "MANIFEST": true, "PROCESS": true, "HEALTH": true, "PORT": true, "AUTH": true, "VERSION": true, "BACKUP": true}
	if !codes[code] {
		code = "PROCESS"
	}
	return Diagnostic{Version, runtime.GOOS + "-" + runtime.GOARCH, stage, fail(code, stage)}
}

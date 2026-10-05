package launch

import (
	"bytes"
	"context"
	"os"
	"os/exec"
	"strings"
)

type ProcessRequest struct {
	Executable string
	Args       []string
	Env        []string
	Stdin      []byte
}

func (ProcessRequest) String() string   { return "[protected process]" }
func (ProcessRequest) GoString() string { return "[protected process]" }

type ProcessResult struct {
	Stdout   []byte
	ExitCode int
}
type Runner interface {
	Run(context.Context, ProcessRequest) (ProcessResult, error)
}
type ExecRunner struct{}

func (ExecRunner) Run(ctx context.Context, q ProcessRequest) (ProcessResult, error) {
	cmd := exec.CommandContext(ctx, q.Executable, q.Args...)
	cmd.Env = q.Env
	cmd.Stdin = bytes.NewReader(q.Stdin)
	var out bytes.Buffer
	cmd.Stdout = &out
	cmd.Stderr = nil
	e := cmd.Run()
	if e != nil {
		return ProcessResult{nil, 1}, fail("PROCESS", "docker")
	}
	return ProcessResult{out.Bytes(), 0}, nil
}
func BuildChildEnv(parent []string) []string {
	allow := map[string]bool{"PATH": true, "HOME": true, "USER": true, "LOGNAME": true, "USERPROFILE": true, "LOCALAPPDATA": true, "APPDATA": true, "SYSTEMROOT": true, "WINDIR": true, "COMSPEC": true, "TMPDIR": true, "TEMP": true, "TMP": true, "DOCKER_CONFIG": true}
	out := []string{}
	for _, s := range parent {
		k, _, ok := strings.Cut(s, "=")
		if ok && allow[strings.ToUpper(k)] {
			out = append(out, s)
		}
	}
	return out
}
func childEnv() []string { return BuildChildEnv(os.Environ()) }

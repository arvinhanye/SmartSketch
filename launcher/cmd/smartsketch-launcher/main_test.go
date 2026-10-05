package main

import (
	"bytes"
	"strings"
	"testing"
)

func TestCLINeverAcceptsSecretArguments(t *testing.T) {
	var out bytes.Buffer
	for _, args := range [][]string{{"--password", "fixture-cli-secret"}, {"--project", "foreign"}, {"serve", "--key=fixture-cli-secret"}} {
		if parseArgs(args, &out) == 0 {
			t.Fatal("unknown arguments accepted")
		}
		if strings.Contains(out.String(), "fixture-cli-secret") {
			t.Fatal("argument echoed")
		}
	}
}
func TestVersionIsOnlyNoninteractiveFlag(t *testing.T) {
	var out bytes.Buffer
	if parseArgs([]string{"--version"}, &out) != 0 || out.Len() == 0 {
		t.Fatal("version failed")
	}
}

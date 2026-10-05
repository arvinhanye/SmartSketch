//go:build !windows

package launch

import "os"

type OSProtector struct{}

func (OSProtector) SecureDir(p string) error  { return os.Chmod(p, 0700) }
func (OSProtector) SecureFile(p string) error { return os.Chmod(p, 0600) }

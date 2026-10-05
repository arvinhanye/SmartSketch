package launch

import (
	"os/exec"
	"os/user"
)

type OSProtector struct{}

func secureACL(p string) error {
	u, e := user.Current()
	if e != nil {
		return e
	}
	cmd := exec.Command("icacls.exe", p, "/inheritance:r", "/grant:r", "*"+u.Uid+":(F)", "*S-1-5-18:(F)")
	if e = cmd.Run(); e != nil {
		return e
	}
	return nil
}
func (OSProtector) SecureDir(p string) error  { return secureACL(p) }
func (OSProtector) SecureFile(p string) error { return secureACL(p) }

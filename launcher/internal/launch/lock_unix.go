//go:build !windows

package launch

import (
	"os"
	"path/filepath"
	"syscall"
)

type InstanceLock struct{ file *os.File }

func AcquireInstance(root string) (*InstanceLock, error) {
	s := Store{Root: root}
	if e := s.ensure(); e != nil {
		return nil, e
	}
	p := filepath.Join(root, "instance.lock")
	if e := noLinks(p); e != nil {
		return nil, e
	}
	f, e := os.OpenFile(p, os.O_CREATE|os.O_RDWR, 0600)
	if e != nil {
		return nil, fail("LOCK", "instance")
	}
	if syscall.Flock(int(f.Fd()), syscall.LOCK_EX|syscall.LOCK_NB) != nil {
		f.Close()
		return nil, fail("LOCK", "instance")
	}
	return &InstanceLock{f}, nil
}
func (l *InstanceLock) Close() error {
	syscall.Flock(int(l.file.Fd()), syscall.LOCK_UN)
	return l.file.Close()
}

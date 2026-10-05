package launch

import (
	"os"
	"path/filepath"
	"syscall"
	"unsafe"
)

type InstanceLock struct {
	file    *os.File
	overlap syscall.Overlapped
}

var lockFile = syscall.NewLazyDLL("kernel32.dll").NewProc("LockFileEx")
var unlockFile = syscall.NewLazyDLL("kernel32.dll").NewProc("UnlockFileEx")

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
	l := &InstanceLock{file: f}
	ok, _, _ := lockFile.Call(f.Fd(), 3, 0, 1, 0, uintptr(unsafe.Pointer(&l.overlap)))
	if ok == 0 {
		f.Close()
		return nil, fail("LOCK", "instance")
	}
	return l, nil
}
func (l *InstanceLock) Close() error {
	unlockFile.Call(l.file.Fd(), 0, 1, 0, uintptr(unsafe.Pointer(&l.overlap)))
	return l.file.Close()
}

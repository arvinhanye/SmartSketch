package launch

import (
	"bytes"
	"os/user"
	"syscall"
	"unsafe"
)

type OSProtector struct{}

var advapi = syscall.NewLazyDLL("advapi32.dll")
var convertSD = advapi.NewProc("ConvertStringSecurityDescriptorToSecurityDescriptorW")
var setFileSD = advapi.NewProc("SetFileSecurityW")
var getFileSD = advapi.NewProc("GetFileSecurityW")
var getSDControl = advapi.NewProc("GetSecurityDescriptorControl")
var getDACL = advapi.NewProc("GetSecurityDescriptorDacl")
var localFree = syscall.NewLazyDLL("kernel32.dll").NewProc("LocalFree")

func secureACL(p string) error {
	u, e := user.Current()
	if e != nil {
		return fail("PERMISSION", "identity")
	}
	if u.Uid == "" {
		return fail("PERMISSION", "identity")
	}
	text, e := syscall.UTF16PtrFromString("D:P(A;;FA;;;" + u.Uid + ")(A;;FA;;;SY)")
	if e != nil {
		return fail("PERMISSION", "identity")
	}
	var sd uintptr
	ok, _, _ := convertSD.Call(uintptr(unsafe.Pointer(text)), 1, uintptr(unsafe.Pointer(&sd)), 0)
	if ok == 0 {
		return fail("PERMISSION", "acl")
	}
	defer localFree.Call(sd)
	path, e := syscall.UTF16PtrFromString(p)
	if e != nil {
		return fail("PERMISSION", "path")
	}
	ok, _, _ = setFileSD.Call(uintptr(unsafe.Pointer(path)), 0x80000004, sd)
	if ok == 0 {
		return fail("PERMISSION", "acl")
	}
	// Read back the protected DACL rather than trusting a chmod or icacls exit.
	var size uint32
	getFileSD.Call(uintptr(unsafe.Pointer(path)), 4, 0, 0, uintptr(unsafe.Pointer(&size)))
	if size == 0 {
		return fail("PERMISSION", "acl-audit")
	}
	buf := make([]byte, size)
	ok, _, _ = getFileSD.Call(uintptr(unsafe.Pointer(path)), 4, uintptr(unsafe.Pointer(&buf[0])), uintptr(size), uintptr(unsafe.Pointer(&size)))
	if ok == 0 {
		return fail("PERMISSION", "acl-audit")
	}
	var control uint16
	var revision uint32
	ok, _, _ = getSDControl.Call(uintptr(unsafe.Pointer(&buf[0])), uintptr(unsafe.Pointer(&control)), uintptr(unsafe.Pointer(&revision)))
	if ok == 0 || control&0x1000 == 0 {
		return fail("PERMISSION", "acl-audit")
	}
	var actualACL, expectedACL uintptr
	var present, defaulted int32
	ok, _, _ = getDACL.Call(uintptr(unsafe.Pointer(&buf[0])), uintptr(unsafe.Pointer(&present)), uintptr(unsafe.Pointer(&actualACL)), uintptr(unsafe.Pointer(&defaulted)))
	if ok == 0 || present == 0 || actualACL == 0 {
		return fail("PERMISSION", "acl-audit")
	}
	ok, _, _ = getDACL.Call(sd, uintptr(unsafe.Pointer(&present)), uintptr(unsafe.Pointer(&expectedACL)), uintptr(unsafe.Pointer(&defaulted)))
	if ok == 0 || expectedACL == 0 {
		return fail("PERMISSION", "acl-audit")
	}
	actualSize := *(*uint16)(unsafe.Pointer(actualACL + 2))
	expectedSize := *(*uint16)(unsafe.Pointer(expectedACL + 2))
	if actualSize != expectedSize || !bytes.Equal(unsafe.Slice((*byte)(unsafe.Pointer(actualACL)), int(actualSize)), unsafe.Slice((*byte)(unsafe.Pointer(expectedACL)), int(expectedSize))) {
		return fail("PERMISSION", "acl-audit")
	}
	return nil
}
func (OSProtector) SecureDir(p string) error  { return secureACL(p) }
func (OSProtector) SecureFile(p string) error { return secureACL(p) }

package launch

import (
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
)

func ResolveRoot(goos, userConfigDir string) (string, error) {
	if goos != "darwin" && goos != "windows" && goos != "linux" || !filepath.IsAbs(userConfigDir) {
		return "", fail("CONFIG", "path")
	}
	return filepath.Join(userConfigDir, "SmartSketch"), nil
}
func FindDocker() (string, error) {
	if p, e := exec.LookPath("docker"); e == nil {
		return p, nil
	}
	home, _ := os.UserHomeDir()
	paths := []string{filepath.Join(home, ".docker", "bin", "docker"), filepath.Join(os.Getenv("LOCALAPPDATA"), "Programs", "DockerDesktop", "resources", "bin", "docker.exe"), filepath.Join(os.Getenv("ProgramFiles"), "Docker", "Docker", "resources", "bin", "docker.exe")}
	for _, p := range paths {
		if st, e := os.Stat(p); e == nil && !st.IsDir() {
			return p, nil
		}
	}
	return "", fail("DOCKER", "environment")
}
func OpenBrowser(raw string) error {
	u, e := url.Parse(raw)
	if e != nil || u.Scheme != "http" || u.Hostname() != "127.0.0.1" || u.User != nil {
		return fail("AUTH", "browser")
	}
	switch runtime.GOOS {
	case "darwin":
		return exec.Command("/usr/bin/open", raw).Run()
	case "windows":
		return exec.Command("rundll32.exe", "url.dll,FileProtocolHandler", raw).Run()
	default:
		return exec.Command("xdg-open", raw).Run()
	}
}

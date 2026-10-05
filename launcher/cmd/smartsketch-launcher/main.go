package main

import (
	"context"
	"fmt"
	"github.com/arvinhanye/SmartSketch/launcher/internal/launch"
	"io"
	"net"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"runtime"
	"time"
)

func parseArgs(args []string, out io.Writer) int {
	if len(args) == 0 || len(args) == 1 && args[0] == "serve" {
		return -1
	}
	if len(args) == 1 && args[0] == "--version" {
		fmt.Fprintln(out, launch.Version)
		return 0
	}
	fmt.Fprintln(out, "启动参数不符合要求。请直接双击入口；不要通过命令行传递口令或密钥。")
	return 2
}
func run() error {
	exe, e := os.Executable()
	if e != nil {
		return fmt.Errorf("启动入口定位失败，请重新解压完整包。")
	}
	bundle := filepath.Dir(exe)
	if filepath.Base(bundle) == "bin" {
		bundle = filepath.Dir(bundle)
	}
	manifestPath := filepath.Join(bundle, "release-manifest.json")
	composePath := filepath.Join(bundle, "compose.release.yaml")
	m, e := launch.LoadManifest(manifestPath)
	if e != nil {
		return e
	}
	if m.Version != launch.Version {
		return fmt.Errorf("启动器版本与发行清单不一致，请重新解压完整发行包。")
	}
	if e = m.VerifyCompose(composePath); e != nil {
		return e
	}
	configDir, e := os.UserConfigDir()
	if runtime.GOOS == "windows" {
		configDir = os.Getenv("LOCALAPPDATA")
	}
	if e != nil || configDir == "" {
		return fmt.Errorf("本机配置目录定位失败。")
	}
	root, e := launch.ResolveRoot(runtime.GOOS, configDir)
	if e != nil {
		return e
	}
	store := &launch.Store{Root: root}
	lock, e := launch.AcquireInstance(root)
	if e != nil {
		return store.Reopen(context.Background())
	}
	defer lock.Close()
	cli, e := launch.FindDocker()
	if e != nil {
		return fmt.Errorf("请先安装并打开 Docker Desktop：https://www.docker.com/products/docker-desktop/；Windows 使用 WSL2 / Linux 容器。")
	}
	if e = store.SeedRelease(manifestPath, composePath, m); e != nil {
		return e
	}
	docker := &launch.Docker{CLI: cli, ComposePath: composePath, EnvPath: filepath.Join(root, ".env"), Manifest: m}
	controller := launch.NewController(store, docker, nil)
	token, e := launch.NewSession()
	if e != nil {
		return e
	}
	listener, e := net.Listen("tcp4", "127.0.0.1:0")
	if e != nil {
		return fmt.Errorf("本机控制端口建立失败。")
	}
	defer listener.Close()
	origin := "http://" + listener.Addr().String()
	server := &http.Server{Handler: launch.NewServer(controller, token, origin), ReadHeaderTimeout: 5 * time.Second, ReadTimeout: 10 * time.Second, WriteTimeout: 15 * time.Second, IdleTimeout: 30 * time.Second, MaxHeaderBytes: 16384}
	if e = store.SaveControl(origin, token); e != nil {
		return e
	}
	defer store.RemoveControl()
	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt)
	defer cancel()
	go controller.Resume(ctx)
	go func() {
		<-ctx.Done()
		shutdown, cancel := context.WithTimeout(context.Background(), 3*time.Second)
		defer cancel()
		_ = server.Shutdown(shutdown)
	}()
	go func() {
		if launch.OpenBrowser(origin+"/#"+secretFragment(token)) != nil {
			fmt.Println("浏览器打开失败，请重新双击入口。")
		}
	}()
	fmt.Println("智绘学途本机控制已启动。关闭此窗口不会停止 Docker 中的业务服务；停止请使用网页按钮。")
	e = server.Serve(listener)
	if e != nil && e != http.ErrServerClosed {
		return fmt.Errorf("本机控制服务已停止。")
	}
	return nil
}

// A session capability is exposed only in the browser launch fragment, never stdout.
func secretFragment(s launch.Secret) string { return launch.SessionFragment(s) }
func main() {
	if code := parseArgs(os.Args[1:], os.Stdout); code >= 0 {
		os.Exit(code)
	}
	if e := run(); e != nil {
		fmt.Fprintln(os.Stderr, e.Error())
		os.Exit(1)
	}
}

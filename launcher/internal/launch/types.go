package launch

import (
	"bytes"
	"encoding/json"
	"errors"
	"io"
)

type Secret struct{ value string }

func NewSecret(v string) Secret             { return Secret{v} }
func (Secret) String() string               { return "[REDACTED]" }
func (Secret) GoString() string             { return "[REDACTED]" }
func (Secret) MarshalJSON() ([]byte, error) { return nil, errors.New("secret serialization disabled") }
func (s *Secret) UnmarshalJSON(b []byte) error {
	var v string
	if json.Unmarshal(b, &v) != nil {
		return fail("FIELD", "config")
	}
	s.value = v
	return nil
}

type EmbeddingConfig struct {
	BaseURL    string `json:"base_url"`
	Model      string `json:"model"`
	APIKey     Secret `json:"api_key"`
	Dimensions int    `json:"dimensions"`
}
type Config struct {
	Embedding                                    EmbeddingConfig
	Neo4jPassword, JWTSecret, ModelCredentialKey Secret
	WebPort                                      int
}
type Phase string

const (
	NEW          Phase = "NEW"
	CONFIGURED   Phase = "CONFIGURED"
	INITIALIZING Phase = "INITIALIZING"
	READY        Phase = "READY"
	STOPPED      Phase = "STOPPED"
	ERROR        Phase = "ERROR"
)

type InstallState struct {
	RestoreHistory                         map[string]string
	DataGeneration                         string
	SchemaVersion                          int
	InstallID, ReleaseVersion              string
	Phase                                  Phase
	Checkpoint, TeacherID, TeacherUsername string
	WebPort                                int
	Fresh                                  bool
}
type SetupInput struct {
	Embedding       EmbeddingConfig `json:"embedding"`
	TeacherUsername string          `json:"teacher_username"`
	TeacherPassword Secret          `json:"teacher_password"`
	ConfirmPassword Secret          `json:"confirm_password"`
	WebPort         int             `json:"web_port"`
}
type Failure struct {
	Code, Stage, Message string
	Retryable            bool
}

func (f *Failure) Error() string { return f.Message }
func fail(code, stage string) *Failure {
	messages := map[string]string{"FIELD": "配置字段不符合要求，请检查后重试。", "CONFIG": "本机配置不完整或存在歧义，请恢复原配置。", "PERMISSION": "配置目录权限保护失败，请检查当前用户权限。", "LOCK": "已有启动器正在运行，请使用已有窗口。", "DOCKER": "Docker 尚未就绪，请打开 Docker Desktop。", "OWNERSHIP": "发现不属于本安装的数据或服务，已停止操作。", "MANIFEST": "发行文件校验失败，请重新下载完整发行包。", "PROCESS": "服务操作失败，请查看当前阶段并重试。", "HEALTH": "服务尚未全部就绪，请检查数据库与任务处理服务。", "PORT": "网站端口被占用，请确认其他端口。", "AUTH": "启动控制会话已失效，请重新双击启动。", "VERSION": "安装版本发生变化，请先确认备份与升级。", "BACKUP": "备份尚未验证，保留原数据并停止升级。"}
	msg, ok := messages[code]
	if !ok {
		msg = "操作未完成，请重试或查看诊断。"
	}
	if code == "BACKUP" && stage == "restore-confirm" {
		msg = "暂存快照已通过检查。请再次点击恢复并确认切换；原数据卷保留。"
	}
	return &Failure{code, stage, msg, true}
}

// Reject duplicate keys before typed decoding; neither pass returns raw input errors.
func strictJSON(b []byte, out any) error {
	d := json.NewDecoder(bytes.NewReader(b))
	var scan func() error
	scan = func() error {
		tok, e := d.Token()
		if e != nil {
			return e
		}
		delim, ok := tok.(json.Delim)
		if !ok {
			return nil
		}
		switch delim {
		case '{':
			seen := map[string]bool{}
			for d.More() {
				k, e := d.Token()
				if e != nil {
					return e
				}
				s, ok := k.(string)
				if !ok || seen[s] {
					return errors.New("duplicate key")
				}
				seen[s] = true
				if e = scan(); e != nil {
					return e
				}
			}
		case '[':
			for d.More() {
				if e := scan(); e != nil {
					return e
				}
			}
		default:
			return errors.New("unexpected delimiter")
		}
		_, e = d.Token()
		return e
	}
	if scan() != nil {
		return fail("FIELD", "input")
	}
	if _, e := d.Token(); e != io.EOF {
		return fail("FIELD", "input")
	}
	d = json.NewDecoder(bytes.NewReader(b))
	d.DisallowUnknownFields()
	if d.Decode(out) != nil {
		return fail("FIELD", "input")
	}
	return nil
}

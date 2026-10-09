# Codex Intel 启动失败排查交接（2026-10-06）

- 自己的工作区：/Users/arvinhan/.codex/worktrees/plan-c-acceptance-review/SmartSketch，分支 codex/cross-platform-startup-design，基线3bc7e9b；原 e92f 他人文档不动。
- STARTUP-15 OPEN，仅定位。报告 docs/reviews/codex-intel-startup-failure-20261006.md。用户附件诊断 PROCESS/unknown；阶段缺失，未证明唯一原因。
- 相同固定已缓存后端镜像 pull：系统最小 PATH exit1，明确 docker-credential-desktop not found；仅补 ~/.docker/bin 后 exit0。Docker引擎 linux；用户本安装 a678a6028b4ace39 没有容器/卷；Fresh true/ERROR/无checkpoint。两份下载二进制SHA一致。
- 最小复现并非用户启动进程实际 PATH；请勿将推断写成完整根因确认。建议用户关闭旧控制器终端后用补 PATH 入口重开，保留全部配置与数据，再导出失败诊断。
- 未修源码/安装包，不重新下载发行、不改 Docker config/凭据/.env/库；真实模型调用0，账本历史值不变。无push/merge/技术冻结。
- 发现的代码后续点：host.FindDocker可绝对找到docker但childEnv无helper目录补全；ExecRunner丢stderr、PROCESS/docker加阶段白名单可能丢失败阶段。修复需先TDD，保留环境白名单和密钥脱敏。
- 验证：对照探针exit1/exit0、manifest inspect exit0、只读Docker检查；本轮完整 verify.sh 未执行，不能写整体门禁/完整启动PASS。旧50362临时日志缺失，不追认结果。

## 第二次诊断后的接续（以此为准）

用户补交 (1).json 与截图，明确 teacher/PROCESS；安装 checkpoint=migrated，Neo4j healthy，三卷已存在，已越过先前 PATH 故障。用户名仅形态确认含大写（不记录原值）。根因：ValidateSetup允许大写，Configure存原样，后端 lower返回规范名，Docker.Bootstrap却大小写精确比较，误判 PROCESS/teacher。原包恢复输入又要求原样相等，不能只在页面填小写解决。

已发行后端摘要断网只读容器+临时SQLite合成复现 exit0：Abc→abc创建成功，启动器精确匹配false，重入同ID/不重置原密码。未挂用户数据/凭据，未读业务库，用户实际账户是否创建仅标可能。完整Go回归未跑（SDK先前临时路径已缺失），整体门禁/实际启动保持OPEN。

下轮需先获得修复范围确认，写新装mixed-case与旧migrated状态恢复回归，再统一Configure/Start/Bootstrap的规范化，保存既有用户ID/首次密码。不得删卷或初始化新账号；只制作本地修正版，替换Release/源码push/merge另行确认。报告已追加P2与具体行号。

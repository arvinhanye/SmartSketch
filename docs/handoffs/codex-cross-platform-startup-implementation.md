# Codex 双击启动实现交接（2026-10-05，验收收集中）

工作区 /Users/arvinhan/.codex/worktrees/plan-c-acceptance-review/SmartSketch，分支 codex/cross-platform-startup-design。依据已批准的设计和九项实施计划。本文件后续补最终提交与门禁结果；不要把当前文档当作已发布安装包。

## 交付范围

Go 私有配置/密钥、状态/锁；固定 Docker 作用域和镜像清单校验；首位教师 stdin 事务工具；发行 Compose 与只读 schema/space/index 探测；180 秒就绪、停止保留数据、恢复检查点；认证本机安装向导；停机整组快照、暂存恢复二次确认；三平台双击脚本、标准库打包程序、仅构建不发布 CI。

已有业务 API/DTO/迁移/依赖保持不变；向量向导写基础设施 .env，不重启已撤销的全站向量配置方案。生成模型仍在业务网站按用户各自配置。

## 验证与失败记录

详细证据见 docs/reviews/codex-startup-platform-validation.md。Go tests/vet/三平台构建、模拟浏览器、定向 Python 与 basic 门禁已取得证据；最终完整门禁和 Docker 场景正在收集。第一轮缓存测试镜像契约漂移/测试编译时序失败已定位，使用一致冻结快照重新验证。

## 命令与环境

开发者使用 Go 1.26.8；scripts/verify/startup.sh 为 full/integration 必跑层，缺 Go 是失败。新用户发行包无需 Python/Node/Go。真实本地测试镜像为 smartsketch-startup-test-*，不可充当正式 GHCR 摘要或平台通过。

本轮不含宿主 .env 的临时快照、随机 ID、独立端口；没有读取/复制业务库、测量文件、真实课程或凭据。保持生成台账 844451/900000、向量12005另计，未补此前暂缓的真实测量。

## OPEN

等待整支独立复审；三平台真实双击、中文路径、Docker 未运行、拉取中断；正式固定摘要匿名拉取；发布授权；用户人工检查与是否技术冻结。stage_c_status OPEN / technical_freeze NOT_PERFORMED。

## 回退

全部为独立本地实现提交，未合并/推送。原 scripts/start.sh 与开发数据未改；停止向导只停止新安装，保留数据。任何真实恢复先完整保留匹配配置/SQLite/Neo4j/镜像，不单独降级代码，不删除旧卷。不清理他人变更。

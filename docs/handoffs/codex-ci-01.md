# CI-01 交接：当前骨架阶段的 GitHub Actions

- **任务与状态**：CI-01，DONE（本地验收通过；GitHub 首次运行待确认）。
- **交付物**：`.github/workflows/ci.yml`；`README.md` 与 `docs/architecture.md` 的 CI 范围说明；`docs/tasks.md` 的认领和验收记录。
- **关键决定**：push、pull request、手动触发同一基础门禁；只运行当前真实存在的 `scripts/verify.sh`，额外执行 `bash -n`；使用只读 `contents` 权限，不依赖密钥或外部服务。尚无前后端依赖清单与测试命令，因此不虚列构建/测试通过。
- **验证**：`./scripts/verify.sh` → `Scaffold verification passed.`；`bash -n scripts/verify.sh` → exit 0；Ruby YAML 解析并检查三类触发器、只读权限、checkout 和 verify 步骤 → PASS；`git diff --check` → exit 0。GitHub 托管运行器上的首轮执行尚未发生。
- **API/数据/配置变更**：无 API 或数据模型变更；新增 GitHub Actions 配置，不使用项目密钥或环境变量。
- **风险与下一步**：CI 目前只覆盖协作骨架。B01/B02/B05/B14 等任务落地后，K11 应扩展真实前后端测试与契约门禁；首次推送后检查 GitHub Actions 运行结果。
- **回滚**：若工作流不符合仓库策略，仅撤销本任务新增的 `.github/workflows/ci.yml` 及相应 CI 说明/任务记录，不触碰其他成员文件。

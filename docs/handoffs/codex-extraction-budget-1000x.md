# EXTRACTION-BUDGET-1000X：本机抽取预算修复

日期：2026-11-15；负责人 Codex；基线 `main@d9d16ca4ed9a083db7e0ce593b1af08b07c73872`。用户要求预算提高 1000 倍，修复后自行重新生成。当前为本机可测试补丁，未提交、推送或合并 PR；模型 API 设置页面不在范围。

## 交付与配置

新增 `LLM_EXTRACTION_MAX_OUTPUT_TOKENS`，个人任务工厂和其他模式共同读取；实体、关系、归一化关系和修复均贯通。配置允许 4096000 输出 token、24000000 请求字节及 64000 窗口；普通默认仍 4096 / 24000 / 64。

本机 API 和 worker 的 Compose 覆盖明确配置：

| 设置 | 旧值 | 当前本机值 |
| --- | ---: | ---: |
| 抽取配置输出 token | 4096 | 4096000 |
| 完整抽取请求字节（含输出预留） | 24000 | 24000000 |
| 每块/小节窗口 | 64 | 64000 |
| 任务 token 软预算 | 500000 | 500000000 |
| 日 token 软预算 | 5000000 | 5000000000 |

官方 DeepSeek 已核验四个模型的实际 `max_tokens` 最高 393216，受 [接口规范](https://api-docs.deepseek.com/api/create-chat-completion/) 与[模型页](https://api-docs.deepseek.com/quick_start/pricing/)约束（2026-11-15）。适配器按准确官方 HTTPS 主机、标准端口、模型白名单限制；未知兼容服务不猜测。主/备用与模型确定之后、审计预写之前计算有效输出，普通/流式/直接适配器发送和无 usage 估算一致。内部窗口规划继续保守预留配置上限；不修改思考开关、语义裁决输出、并发、超时或关系语义规则。

## 验证

- 配置与生产工厂 RED：6 failed / 2 passed（新增配置原先忽略、既有字节/窗口校验拒绝）；GREEN 8 passed。覆盖个人/其他模式、三类抽取及修复、29 实体完整窗口和边界。
- 供应商限制 RED：8 failed / 6 passed；GREEN 14 passed。含实际临时 SQLite、无 usage、主备与流式；更大定向组合 417 passed。
- 抽取/窗口/个人凭据/思考设置回归：55 passed；测试索引同步后守卫 1 passed。上述组合存在重叠，不相加当独立覆盖数。
- 独立只读复审：6 产品文件、2 新测试均检查，无确认缺陷；独立 46 passed，另两条“DeepSeek 主用失败转未知备用供应商后恢复原输出额度”反例通过。
- 实际第 3 章快照离线重放：29 实体 / 3 块，旧完整请求 42628 字节 -> `window_limit`；新请求保守估算 16410244 字节 <24000000，完整 29 实体保留于 1 窗口，0 模型调用。证据 `.demo/budget-1000x-20261115/window-replay.json`。
- `PATH="/Users/arvinhan/Desktop/SmartSketch-main/.venv/bin:$PATH" ./scripts/verify.sh`：exit 0，包含 25 项门禁负向检查与所有契约回归；`git diff --check` 通过。
- 基于干净 main 归档，仅覆盖 6 个本次后端文件构建；源码哈希与工作区一致。镜像 `smartsketch-backend:budget-1000x-d9d16ca`，ID `sha256:cfa75df7cedfea7f3c56364803f5167dec63a38c9b2b6dff6e32850c02329705`，标签记录主线 revision 和本地 patch。
- 实际 API/worker 的 6 个修改文件 SHA256 均与工作区一致，均读取上述 5 个值，`LLM_MODE=personal`；BE-05 开关仍开启。API/worker/web/Neo4j 均 healthy，`http://127.0.0.1:8080/health` 返回 ok。API 重建后对原 web 执行 Nginx reload 刷新上游地址，未重建前端。
- 切换前确认无处理中的任务；切换后原课程 52 节点、5 边、52 次调用及任务、计划、检查点逐项不变。没有真实模型调用、迁移或图谱修改。

## 重测、限制与恢复

请用户新建空白测试课程，只导入 `第3章_栈队列与递归_单章起步.md` 再生成。旧检查点固定原 24000/64 策略，不能在旧任务续跑验证新预算；在新输出上限下旧策略还可能更早报 input_budget。原课程保留供前后比较。工程验证只证明预算阻塞消除与请求接线正确；真实图谱边数、孤立率、误合并、重复及语义正确性待用户重测。

此为当前运行的本机测试补丁，不是官方 Release。原安装包/清单/`.env` 保持原状，旧启动器重新创建服务会恢复旧镜像及旧预算。下次重开应使用本工作树忽略目录的本机切换脚本，或在修复正式合入并打包后升级：

- 应用：`python3 .demo/budget-1000x-20261115/switch_backend.py`。
- 回退：同一脚本追加 `--rollback`；只重建 API/worker，不改变数据卷，不回退现有主线前端。重建后必要时对 web 执行 `nginx -s reload`。
- 覆盖文件与证据均在 `.demo/budget-1000x-20261115/`；目录不入库，未复制 `.env` 或凭据。旧镜像保留，没有数据库迁移或数据恢复步骤。

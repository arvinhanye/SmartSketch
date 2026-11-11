# OPT-06B：extract_task.py 按职责拆分

- task_id：OPT-06B；负责人 Codex；状态 DONE_LOCAL（实现、定向/全量、共用门禁及独立审查完成；仅本地交付）。
- 本地分支 `codex/opt-06b-extraction`；本项基线 `3974731`，未来 PR 以 `codex/opt-06d-student-graph` 为 base；暂不推送或合并远端 PR。

## 文件与边界

`workers/extract_task.py` 从 1020 行降为 260 行，保留 run_extract_stage、fail_for_credential、run_once 装配入口，显式再导出旧符号。新增 `workers/extraction/`：types.py（类型/阈值/日志）、candidates.py（序列化/分组/候选读取）、units.py（单元执行/重试）、state.py（租约边界/进度/检查点与终态写入）、dispatch.py（有界派发/阶段推进）。模块依赖无环，底层不反向依赖入口。

函数/类体原样搬移；保留默认并发 4、块与小节阶段屏障、输出排序、失败阈值、租约/取消/事务边界。logger 显式使用旧类别 `app.workers.extract_task`。原 `_Dispatcher` 类对象在入口继续可用，已有测试注入点不变。未合入另一个 `codex/extraction-perf` 分支的并发或调度改动。

## 验证

- AST/运行时审计：**60 定义 / 47 签名**一致、__all__ 内容/顺序不变、旧入口与新归属对象身份相同、logger 类别不变。证据 `b-audit.json`。
- `PYTHONPATH=src/backend .venv/bin/python -m pytest tests/backend/test_e12.py tests/backend/test_demo_mode.py tests/backend/test_c02_phase_logs.py tests/backend/test_k02_run.py -q -p no:cacheprovider`：**87 passed，exit 0**（37.44 秒）。
- `PATH="$PWD/.venv/bin:$PATH" scripts/verify/backend.sh full`：**4264 passed / 27 登记 skip，gate PASS，exit 0**；证据 `b-backend-full.log` / `.exit`。
- 最终共用 `./scripts/verify.sh` **exit 0**；独立审查无可操作问题，见 `final-review.md`；完整证据目录 `.superpowers/sdd/2026-11-10-opt-06-responsibility-split/`。

## 接口、数据与风险

无 API、契约、数据库、依赖或配置默认值变更。仅同步架构内部映射；回滚仅撤销本项提交，无数据迁移。后续整合 EXTRACT-PERF 时应在新调度模块上移植并重新回归，不直接覆盖旧入口。本项本地验收完成。定义搬移改变 __module__/repr 等源码归属元数据；审查未发现业务或持久化消费者依赖，未新增任意旧模块属性重新赋值的动态转发能力。

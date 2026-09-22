# 契约测试

归 Backend Agent（`src/contracts/` 单一写入方，ADR-004）。

- 验证生成物与真源一致：等价于 `./scripts/gen-contracts.sh --check`，由 `scripts/verify/contracts.sh` 调用。
- 验证跨端约定：SSE 事件可被前端类型消费、枚举取值与 ADR-005 状态机一致、图谱交换文件能往返序列化。
- 契约变更必须先改真源再跑测试；发现缺口回送后端 Agent，不在前端本地打补丁。

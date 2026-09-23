# 契约测试

归 Backend Agent（`src/contracts/` 单一写入方，ADR-004）。

## 现有

[`test_contracts.py`](test_contracts.py) —— **门禁自身的负向测试**。门禁曾经在缺 PyYAML 时
静默 `exit 0`（codex 审查 R02），所以它需要自己的测试。覆盖：

| 类别 | 用例 |
| --- | --- |
| 依赖 | 缺 PyYAML 必须失败；`--allow-scaffold` 显式降级才可退出 0 |
| 真源结构 | 坏 YAML、无法解析的 `$ref` |
| 命名与枚举（ADR-008 / ADR-005） | 关系类型别名、状态机缺 `persisting`、领域状态混进 `ErrorCode` |
| 路径（ADR-004 第 8 条） | 缺 `/api/v1` 前缀 |
| 来源引用（ADR-003 / R03） | `answered` 不要求引用、引用不强制可定位、`page` 可为 null、`not_covered` 不给机读原因 |
| 问答事件（R04） | 宽松 `ChatEvent`（`{}` 会通过）、`done` 不带最终正文 |
| 状态机一致（R05） | 规格漏 `persisting`、架构漏 `cancelled` |
| 实例级 | codex 报告里的两个负例必须被拒；带页码或带章节的真实引用必须通过 |

第一条用例是**测试的测试**：证明未被破坏的临时工作区是绿的，否则所有「必须失败」
的用例都会假阳性通过。

运行：

```bash
python3 tests/contracts/test_contracts.py     # 不需要 pytest
```

`scripts/verify/contracts.sh` 会自动跑它。

## 待补（M0-09 之后）

- 生成物与真源一致：`./scripts/gen-contracts.sh --check` 已覆盖 openapi.json 与独立
  JSON Schema；Pydantic 与 TS 两个阶段要等生成器安装后才纳入（见 `src/contracts/toolchain.txt`）。
- 跨端约定：SSE 事件可被前端类型消费、图谱交换文件能往返序列化。

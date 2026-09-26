# Claude 交接：ADR-022 上传上限经接口下发

- task_id: ADR-022
- review_status: ready_for_review
- 分支：`claude/project-thread-sp1d3a`（与 E11、H02、H12、ADR-021 同一 PR，独立提交）
- 起因：H02 交接待决「前端 50 MiB 上限写死，与 `UPLOAD_MAX_BYTES` 可能不一致」；ArvinHan 2026-09-26 要求「一起处理掉」。

## 改动文件

| 文件 | 说明 |
| --- | --- |
| `docs/decisions.md` | 新增 ADR-022 |
| `specs/identity-access.md` | 访问矩阵新增 `getUploadPolicy`（课程教师） |
| `docs/integrations.md` | `UPLOAD_MAX_BYTES` 行注明经 `getUploadPolicy` 下发 |
| `src/contracts/api.v1.yaml` + 生成物 | `GET /api/v1/courses/{cid}/upload-policy`；schema `UploadPolicy {max_bytes: integer ≥ 1}`，`additionalProperties: false` |
| `src/backend/app/schemas/materials.py` | `UploadPolicy` |
| `src/backend/app/api/materials.py` | `policy_router` + `get_upload_policy`（`Depends(course_teacher)`，返回 `settings.UPLOAD_MAX_BYTES`） |
| `src/backend/app/main.py` | 注册 `policy_router` |
| `tests/backend/test_adr022.py` | 7 个用例：配置值、默认 50 MiB、与 413 `limit_bytes` 同源、访问矩阵、OpenAPI |
| `src/frontend/src/api/materials.ts` | `uploadPolicy(cid, control?)` |
| `src/frontend/src/composables/useMaterials.ts` | 删除 `MATERIAL_MAX_BYTES`；`maxBytes` 状态；`validateMaterialFile(file, maxBytes)`；进入页面（确认教师后）与列表并行读取策略；413 `limit_bytes` 回填；导出 `limitText` |
| `src/frontend/src/views/MaterialsView.vue` | 提示用 `limitText`，未知时显示「文件大小上限以服务器为准」 |
| `tests/frontend/h02.test.ts` | 79 个用例（新增 7 个，旧用例改为显式传上限） |

## 行为

- 策略读取成功：本地校验与提示都用服务端值（可大于或小于 50 MiB）。
- 读取失败或尚未返回：不做本地大小校验，页面其余功能不受影响，服务器 413 兜底。
- 收到 413 且带合法 `limit_bytes`：更新本地上限，之后的超限文件在本地拦截。
- 非教师（`my_role !== 'teacher'`）不请求策略。
- 格式白名单仍写在前端（契约 `DocumentFormat` 闭集）。

## 验证（实际结果）

| 命令 | 结果 |
| --- | --- |
| `python -m pytest tests/backend/test_adr022.py -q`（实现前） | 7 failed |
| 同上（实现后） | 7 passed |
| `python -m pytest tests/backend -q` | 2764 passed，1 条既有警告 |
| `npx vitest run ../../tests/frontend/h02.test.ts`（实现前） | 7 failed / 72 passed |
| 同上（实现后） | 79 passed |
| `npx vitest run`（前端全量） | 9 files，262 passed |
| `npm run type-check`、`npm run build` | exit 0 |
| `./scripts/gen-contracts.sh --check`、`./scripts/verify.sh`、`git diff --check` | exit 0 |

反向篡改（改回后 `cmp` 一致）：忽略策略 → 4 failed；不按 413 回填 → 1 failed；未知时回退 50 MiB → 2 failed；角色检查前请求策略 → 1 failed。

## 接口 / 数据变更

- 新操作 `getUploadPolicy`、新 schema `UploadPolicy`；无数据库迁移、无新环境变量。
- 前端导出 `MATERIAL_MAX_BYTES` 已删除；`validateMaterialFile` 签名改为两个参数。

## 风险

- 多进程部署若各进程 `UPLOAD_MAX_BYTES` 不同，策略值与实际处理上传的进程可能不一致；413 回填可纠正。

## 回滚

`git revert` 本提交；前端恢复固定 50 MiB，契约回到无 `getUploadPolicy`。

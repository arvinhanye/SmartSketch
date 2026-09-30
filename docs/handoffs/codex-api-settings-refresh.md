# codex-api-settings-refresh
输入：用户要求两块 API 独立测试、结果小窗口（延迟/成败）、模型自动识别与下拉、本页暖纸墨色。
输出：后端 service/routes、前端 client/dialog/view、定向测试及依赖 alias；已同步原型产物并清理旧 assets。
接口：新增 POST /api/v1/api-settings/models；POST /test 返回 {ok, latency_ms, detail, error}，保持向量迁移门禁。
验证：后端指定离线单测 6 passed；前端定向测试因依赖解析失败，2 次重试达限未执行断言；type-check 修复后 exit 0；build exit 0。
未做：真实服务商调用、全量测试、e2e、迁移；已有服务未运行，唯一 smoke 跳过，原型弹窗尚未运行态验证。
偏差：修复模板类型错误后为同步最终原型额外 build 一次；前端 alias 已修正至本机 ESM 入口，未继续重试。
风险：服务商不支持 /models 时允许手填；在线模式保存未选模型后，重启仍受既有配置校验约束，须先选择模型。
提交：按用户明确要求本地提交，覆盖执行单“不 commit”；不推送，用户提供的 docs/plans 保留原样未暂存。

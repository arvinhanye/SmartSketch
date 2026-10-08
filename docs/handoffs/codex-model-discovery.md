# 模型供应商与模型发现交接

用户要求供应商选择，并在输入 API Key 后识别可用模型供选择，同时支持手填。

## 实现

- 当前本地分支 `codex/courses-model-settings-ui`，沿用 PR #322 文档与现有页面改造；工作树未提交/推送。
- 设置页增加 DeepSeek、OpenAI、硅基流动、阿里云百炼与自定义 OpenAI 兼容选项；预设地址可编辑。切换供应商清空旧 Key 与模型名，不自动把旧 Key 发往新地址。
- 新 Key 输入停止 800ms 后自动获取；可用「刷新模型列表」主动刷新，包括使用同地址已保存密钥。列表选择写入模型名，手填始终可用；不自动替换手填值。失败或空列表仍可手填并保存。
- 新鉴权只读 `POST /api/v1/me/model-config/models` 转发兼容 `GET /models`。有新 Key 时不保存；无 Key 仅复用本人精确相同地址的保存配置，不改变最近连接测试状态。
- 沿用出站公网 DNS 检查、固定连接地址、TLS 主机验证与 15 秒总预算；不跟随重定向。响应限制 1MiB / 1000 模型 / 128 字符名称，仅返回列表与固定错误类别；拒绝回显 Key 的名称。
- 列表请求在 Key、地址、会话变化或卸载时作废/取消；不在本地存储缓存 Key。供应商列表不等于模型兼容性验证，保存前仍可测试连接。
- 不含数据迁移、真实供应商调用、课程发布或部署。

## 验收

- 先写前后端测试并确认缺实现 RED，随后 GREEN。
- 后端新发现与 N07/N08/L05 出站/原配置回归：74 PASS。
- 全量前端：61 文件 / 1169 PASS；随后补会话取消、手填保存与 Key 一致性回归，发现测试共 6 PASS。
- type-check 与 build PASS（既有 G6 分块大小警告）。
- `scripts/verify.sh basic` PASS，含真源/生成同步与 B14 生成漂移检查。生成器已在用户 Python Scripts 目录，检查时显式加入 PATH。
- 浏览器 1440/390 两宽度：输入 Key 自动获取、下拉/手填、供应商切换、无溢出与无运行错误 PASS；全部假模型响应。
- 已重启本仓库 API；实际 8321 路由存在、未登录 401、登录后不安全地址 blocked_address，无外部调用。前端仍在 5322。
- 只读复审修复模型发现 trim Key 与保存不一致的问题。

## 供应商地址参考

- [DeepSeek](https://api-docs.deepseek.com/en/)
- [OpenAI 模型列表](https://developers.openai.com/api/reference/resources/models/methods/list)
- [硅基流动模型列表](https://api-docs.siliconflow.cn/docs/api/models-get)
- [百炼兼容地址与地域说明](https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope)

供应商可能不开放兼容模型目录；这类服务保持手动模型输入，地址可按账号所在地域修改。

# 模型列表请求参数修复（2026-10-01）
- 根因：前端传 list_path，后端 _resolve 仅分离 kind，导致在请求供应商之前被配置白名单拒绝。
- 交付：仅在 list_models 调用 _resolve 前分离 list_path；源码与 app 后端同步，不放宽配置白名单。
- 规格：specs/api-settings.md 已说明 list_path 属于请求参数，不能持久保存。
- 验证：新增回归先复现 llm/embedding 两个失败子用例；修复后定向 unittest 4 passed。
- 命令：Python portable_bootstrap.py -m unittest discover -s tests -p test_api_settings.py -k test_model_discovery -k test_list_path_is_not_a_persisted_config_field。
- 未执行真实 API、数据库变更、全量测试、前端构建、服务重启或 Git 提交/推送。
- 运行态需重启软件后点击获取模型列表确认；本轮保留 DeepSeek 其他未提交修改。

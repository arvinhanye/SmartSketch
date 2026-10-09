# Additional provider presets

2026-10-08; baseline0788a62; branch codex/ui-polish-model-discovery. Frontend-only request to add more providers; no credentials/settings persisted and no backend changes.

General API adds Kimi, Zhipu GLM, Volcengine Ark/Doubao, MiniMax, Baidu Qianfan and Tencent Hunyuan. Every entry now declares embedding eligibility; embedding panel adds Zhipu and Ark and excludes generation-only presets. URLs refer to regular API endpoints, not subscription Coding Plan endpoints. Compatible API model abilities, directory availability and dimensions must still be verified with the user's actual key using Test Connection. No account-specific endpoint/model IDs are invented.

Official sources checked on2026-10-08:
- Kimi: https://platform.kimi.com/blog/posts/kimi-api-quick-start-guide
- Zhipu endpoint: https://docs.bigmodel.cn/cn/best-practice/case/ai-search-engine ; embedding documented in https://docs.bigmodel.cn/llms.txt
- Ark: https://docs.volcengine.com/docs/ark/quick-start?lang=zh ; text embeddings endpoint example https://api.volcengine.com/api-docs/view?action=Embeddings&serviceCode=ark&version=2024-01-01
- MiniMax current mainland URL: https://platform.minimax.cn/docs/api-reference/text-openai-api
- Qianfan: https://github.com/baidubce/bce-qianfan-sdk ; model list https://cloud.baidu.com/doc/qianfan-api/s/Dmba8k71y
- Hunyuan: https://cloud.tencent.com/document/product/1729/111007

Validation:four related frontend suites32 passed; type-check and build passed (existing chunk advisory). Live teacher/student browser checks passed for all six preset URL selections, key/model resets,11 general options and6 embedding options (including custom), and no embedding panel for students. No real provider call was made by browser checks; directory requests intercepted locally. `scripts/verify.sh basic` passed with exit0, contract parity and regression gates. The initial foreground invocation ended before full gate output; the complete background rerun produced both PASS markers and an explicit exit0 artifact. Only task files committed locally; no push.

Changed files:useModelDiscovery.ts provider metadata and EmbeddingSettings.vue eligibility filter, specification/task/handoff docs. Rollback:revert task commit, no DB migration needed. Refresh http://127.0.0.1:5322/settings/model to inspect.

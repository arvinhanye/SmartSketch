# Codex 本机 API 设置交接

输入：用户提供的源码与两份本机 API 凭据；凭据不写入本文件。输出：教师侧栏 API 设置页面、后台 GET/PUT/test 及 DPAPI 持久化；保存后重启生效。接口与边界见 specs/api-settings.md。

验证：2 项单元测试通过；前端 vue-tsc 与 Vite build exit 0；本机 smoke 检查访问权限、密钥隐藏、空值保留、在线 DeepSeek/演示向量、向量切换门禁通过；浏览器实际页面确认通过；供应商接口各一次最短连接测试成功。按用户要求不跑全量 verify.sh。

运行：app 为发行目录，SmartSketch_src 为对应源码，两处后端修改同步；前端 dist 已复制 app/web。launcher/local-runtime.json 记录已有 Python/Java/Neo4j 路径。嵌入式 Python 经 portable_bootstrap.py 确保当前发行代码优先。修复停止脚本斜杠路径比较。

凭据：%LOCALAPPDATA%/SmartSketch-External/api-settings.json，Windows DPAPI 绑定当前用户；不回显。DeepSeek 在线生效。通义 text-embedding-v4/1024 配置已保存，演示向量继续生效。用户明确选择不迁移；没有发送课程内容生成通义向量。自动审批曾拒绝迁移，后按用户选择保留演示向量。

备份：应用数据目录 backups/full-before-tongyi-* 保存停机数据库、Neo4j home data 和配置。未执行向量迁移，无需回滚。后续切换向量模型需要明确授权、停机、备份和 reembed.py；默认模式仍 demo，不能直接在页面跨空间切换。

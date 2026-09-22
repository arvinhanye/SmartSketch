# api/

FastAPI 路由与依赖注入，只做协议转换。依赖方向 `api → schemas → services → repositories`，不得反向。

不放：业务编排与领域规则（→ `services/`）、Cypher 与查询字符串拼接（→ `repositories/`）、对外 DTO 定义（→ `src/contracts/`）。

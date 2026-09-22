# schemas/

后端内部模型与依赖装配。对外 DTO 一律从 `src/contracts/` 导入（ADR-004）。

不放：对外 DTO 的重复定义或再声明、持久化实现、业务规则。

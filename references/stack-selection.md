# 技术选型（stack selection，本技能样板）

> 第二层访谈的**规则与决策表**唯一权威在 agent-skills-index 的 `conventions/stack-interview.md`；
> 本文只做两件事：把决策表**映射到业务档位**，并给出**技术栈委托表**。每个决策点保留开发者选择权 + 利害说明。

## 1. 档位 → 技术选型（每档推荐 + 利害 + 换档触发器）

| 档位 | 语言 | 数据库 | 事件 | 缓存/会话 | 部署 | CI/观测 |
| --- | --- | --- | --- | --- | --- | --- |
| L0 最小验证 | Go 或 Node（跟团队） | Postgres（或 SQLite 单机） | 无 MQ（outbox 直连） | 无/内存 | 单机 compose | Actions + 冒烟 |
| L1 独立经营 | Go（默认） | Postgres | 无 MQ | Redis（会话/限流） | 单机 compose | Actions + Sentry + k6 基线 |
| L2 商业产品 | Go | Postgres（分区/读写分离预案） | 按信号上真 MQ | Redis | compose → 多机预案 | Actions + 告警 + 压测门禁 |
| L3 可复用基础设施 | 各产品自治 | 各产品自治 + 身份层独立 | outbox 事实源 + relay | 按产品 | 按产品（vps D 形态） | 全链路观测 + 概念注册表 |

利害速记：SQLite 省运维但多实例无解；MySQL 云上便宜但幂等唯一索引的 NULL 语义要显式兜底；
serverless 与 outbox relay 长驻冲突；官方回调必须有备案域名——详见 stack-interview §2/§3。

## 2. 技术栈委托表（选型 → 执行技能）

| 选型/任务 | 执行层技能 |
| --- | --- |
| Go 后端实现 | golang-database（事务/锁/池）、golang-concurrency（扣减/claim）、golang-testing、golang-observability |
| 前后端契约 | api-contract-typing（openapi 单一事实源） |
| 日志与链路 | logging-system-builder（trace_id 贯通） |
| 测试/压测门禁 | quality-gate-builder（三模拟器 + k6 基线） |
| 服务器加固 | server-hardening |
| 迁移/重建 | vps-migrator |

## 3. 与分支表的关系

SKILL.md 第一步的"技术栈"分支（`go_next_pg / node_next_pg / existing_stack`）不再是被动默认值——
它由第二层访谈的"团队语言能力"驱动，落档后按本表取值，并在分支决策表里写出理由与利害。

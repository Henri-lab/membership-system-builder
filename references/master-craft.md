# 老师傅的隐形知识：十篇权威判据与五个评审测试（master-craft）

> 学习资料。回答高频问题：「这些设计经验是谁总结的？有没有权威源头？是不是我瞎编的？」
> 结论先讲：本技能散落各处（不变量、账本、判定手册、经验账本）的「老师傅直觉」绝大多数不是自创玄学，
> 而是几篇业界公认文献与工程实践的**可操作化翻译**。本文把源头、原话、以及它们在 MSP 里的落点逐条对齐，
> 并浓缩成五个可以在代码评审时直接使用的测试。
> 配套阅读：[design-judgment.md](design-judgment.md)（加字段 vs 加对象）、[design-walkthrough.md](design-walkthrough.md)（正常与边界例子）、[lessons-log.md](lessons-log.md)（真实教训）。

## 0. 诚实声明（provenance）

- `lessons-log.md` 的 L-001~L-052 是本项目真实踩坑 + 评审推理的原始素材；
- 本文的「权威判据」来自 §1 的论文 / 标准 / 官方文档，均已核对出处（链接见 §5）；
- agent 做的工作是：把文献翻译成可执行判据 + 对齐到 MSP 的 INV / OP / T 锚点，不声称原创理论；
- 反过来，本项目的真实教训也印证了这些文献——例如 L-010（单列 `event_id` 顶掉合法数据）正是
  CloudEvents `(id, source)` 唯一性在账本领域的同构版。

## 1. 十篇权威判据（源头 → 一句话 → MSP 落点 → 反问句）

### 1.1 Helland《The I's Have It》（CIDR 2019）

**身份（Identity）、不可变（Immutability）、幂等（Idempotence）、可互换（Interchangeability）是分布式计算的骨架。**

- 翻译：先定义「什么算同一次业务事实」（identity），事实一旦记下不再改（immutability），
  重复到达不重复生效（idempotence），同值可互换（interchangeability）。
- MSP 落点：INV-14/15/26、ledger.md §4。
- 反问：这条记录的身份由什么唯一确定？身份没想清楚之前，幂等键必然是错的。

### 1.2 Helland《Immutability Changes Everything》（CACM 2016）

> "Accountants don't use erasers, or they may go to jail."（会计不用橡皮擦——用了可能会坐牢。）

- 翻译：纠错不是擦掉旧记录，而是追加一条反向记录；余额永远是被推导出来的。
- MSP 落点：INV-14/24、ledger.md L2/L3、T-29。
- 反问：出现「改一笔历史账」的需求时，改成「插一条冲销 / 调整分录」是否同样满足业务？

### 1.3 Helland《Life beyond Distributed Transactions》（CIDR 2007）+《Building on Quicksand》（CIDR 2009）

**跨系统分布式事务不可持续；把系统切成「实体」（Entity = 原子事务作用域），实体之间用「活动」（Activity）记录不确定性并逐步收敛。**

- 翻译：单点内强一致，跨点靠「状态机 + 事件 + 补偿」，别指望一把大锁锁全局。
- MSP 落点：模块边界（订单/权益/积分/退款）、INV-18/19/25、退款状态机 `processing → succeeded/failed`。
- 反问：这个不变量能在一个事务里闭环吗？不能，就把它拆成「状态 + 事件 + 幂等消费」。

### 1.4 Helland《Idempotence Is Not a Medical Condition》（ACM Queue 2012）

**消息投递只承诺「至少一次」或「至多一次」，不存在传输层给的「恰好一次」；幂等必须由业务层自己保证。**

- 翻译：重复是常态、不是异常。幂等要建立在「业务事实」层面，而不是传输层。
- MSP 落点：INV-7/19/26、ledger.md §4 三层幂等键、通知层 `nonce` + 入账层结构化键两层防线、L-051。
- 反问：同一条消息投递两次，业务结果是否逐字节相同？防重复的「键」具体是什么？

### 1.5 Kleppmann《Turning the database inside-out》（2014/2015）

**不可变日志是事实源；表状态、索引、缓存都是派生数据（derived data）——**

> "if you drop the index, that doesn't delete any data from your database."
（删掉索引不删任何数据。）

- 翻译：账本是源，余额是派生。能重建的东西（索引/缓存/物化视图）可以随时删了重算。
- MSP 落点：ledger.md L1/L4 与三种合规策略（A/B/C）、T-30、design-judgment.md 的「删表重建测试」。
- 反问：这张表删掉，事实（钱/权益）丢不丢？丢 = 事实源；不丢 = 派生缓存。

### 1.6 Fowler《Effectivity / Temporal Object / Bitemporal History》

> "Add a time period to an object to show when it is effective."（给对象加一个时间段，表达它何时生效。）

时间有两个维度：有效期（valid time）与记录时间（record time）；会变的对象 = 带区间的版本段。

- 翻译：可变日期是雷。把「从 X 到 Y 有效」建模成不可变的**段**，变更 = 追加新段，不是改旧段。
- MSP 落点：INV-9/16/28/29、段回收（OP-R2）、试用/争议按段冻结（OP-T2/D1）、T-41~46。
- 反问：改日期字段是否等价于「生成新段 + 记录变更」？不能改写区间历史。

### 1.7 Evans《Domain-Driven Design》（2003）

**聚合（Aggregate）是事务一致性边界：聚合内不变量即时成立，跨聚合只能最终一致。**

- 翻译：先划聚合再定表；一个不变量跨两个聚合 = 边界画错了。
- MSP 落点：模块划分、INV-12（余额与账本同事务）、INV-16（不能完整回滚就不许退款成功）、L-050（扩展表同点创建）。
- 反问：这个不变量跨了哪个聚合？把它关回一个事务，或显式声明它的收敛时间窗与补偿。

### 1.8 CloudEvents v1.0 + IETF Idempotency-Key 草案

**事件唯一性由 `(id, source)` 共同决定（不是 `id` 单独唯一）；幂等键与请求体绑定、服务端保留、在途重试返回 409。**

- MSP 落点：events.md 信封、INV-15、ledger.md §4 `(source_event_id, ref)`、prior-art.md 映射表。
- 反问：信封 `id` 由生产方生成且唯一吗？幂等键和请求体绑定了吗、保留期多久？

### 1.9 Stripe 公开工程实践

**金额只用整数最小单位；所有写接口幂等；余额是流水的派生视图；复杂状态显式建模为状态机。**

官方原话："You can remove keys from the system automatically after they're at least 24 hours old."
（幂等键至少保留 24 小时，之后才允许清理。）

- MSP 落点：INV-1/2/28、ledger.md `balance_after`、订阅/退款/争议状态机、prior-art.md。
- 反问：金额字段的「单位」在哪声明？这个写接口重试会二次扣款吗？

### 1.10 Amazon Builders Library《Ensuring rollback safety during deployments》

**部署必须可安全回滚：旧版本能读新数据、新版本能读旧数据，schema 演进走 expand → migrate → contract。**

- 翻译：上线新功能先问「回滚路径」。迁移可逆、协议只加不改、新字段先给默认值再收紧。
- MSP 落点：extensions.md 仅加法演进与日期化版本、lessons-log.md L-027/28（多网络绑定 0.0.0.0、网关数据卷事故）、migration 顺序约定。
- 反问：今天部署 v2 发现 bug 要回 v1，v1 能正确读 v2 写下的数据吗？

## 2. 五条反直觉规则（老师傅才反复强调的）

1. **存「发生了什么」，不存「现在是什么」**——「现在是什么」永远可以由事件重算出来。
2. **幂等键跟着业务事实走，不跟着请求走**——`(event_id, ref)` 而不是 `request_id`；一个事件一单多项时单列键必然顶掉合法数据（L-010）。
3. **并发不是加锁，是条件更新**——把期望值写进 UPDATE 的 WHERE（`WHERE balance >= :x`），影响行数 0 就是输给了别人（ledger.md C2/C3）。
4. **修正是新事实，不是改旧事实**——退款是反向分录，改价是快照/新版本，改期是新段。
5. **跨模块的「一个动作」其实是一串事件**——「支付成功」不是一次 UPDATE，而是
   `order.paid → 履约 → 权益 → 积分` 的一串幂等步骤，任何一步都要能安全重放（INV-19/25/26）。

## 3. 五个老师傅测试（代码评审直接抄）

> 前三个与 [design-judgment.md](design-judgment.md) 的「三个杀手测试」同源；这里补出处，并新增并发、回滚两个。
> 这五条已升格为验收规则：[msp/conformance.md](msp/conformance.md) §3 的 D-1~D-5，任何实现都必须通过且不可豁免。
> 操作化定义（必检问题/各域表述/通过证据）的唯一权威在 quality-gate-builder 的 design-judgments.md；本文只保留出处溯源。

| # | 测试 | 一句话 | 命中哪条判据 |
| --- | --- | --- | --- |
| 1 | 删表重建 | 删掉这张表，钱/权益事实还能重建吗？ | 1.5 Kleppmann；ledger L1/L4 |
| 2 | 一年后审计 | 一年后能指着一条不再变化的记录回答「为什么是这个数」吗？ | 1.2 Helland；INV-24 |
| 3 | 并发同发 | 两个相同请求同时到：恰好一个赢，另一个知道为什么输？ | 1.7 / 规则 3；INV-11、ledger C2 |
| 4 | 事件重放 | 同一条事件重放两次，结果逐字节一致吗？ | 1.1/1.4 Helland；INV-15/26 |
| 5 | 回滚演练 | 部署 v2 出 bug 回 v1：数据完整、能读、能继续跑吗？ | 1.10 AWS；extensions.md |

## 4. 新手直觉 vs 老师傅做法

| 场景 | 新手直觉 | 老师傅做法 | 依据 |
| --- | --- | --- | --- |
| 金额 | float / double | 整数最小单位 + 币种 | INV-1；Stripe |
| 余额扣减 | 先 SELECT 再 UPDATE | 条件更新 / 行锁 | INV-11；ledger C2/C3 |
| 重复回调 | 「应该不会重复吧」 | 双层防线（nonce + 结构化键） | INV-7/15 |
| 订单改价 | 直接 UPDATE | 快照 + 新版本 | INV-2 |
| 退款 | 把订单改成 refunded | 工单 + 负向分录 + 段回收 | INV-16/28 |
| 改到期时间 | 改 expired_at | 新段 + 记录 | Fowler；INV-9/16 |
| 跨模块一致 | 一个大事务 | outbox + 幂等消费 | Helland 2007；INV-18/19 |
| 上线新表 | 直接 NOT NULL | expand → migrate → contract | AWS；extensions.md |

## 5. 出处清单

- Helland, The I's Have It（CIDR 2019）：<https://www.cidrdb.org/cidr2019/gongshow/abstracts/cidr2019_161.pdf>
- Helland, Immutability Changes Everything（CACM 2016）：<https://cacm.acm.org/practice/immutability-changes-everything/>
- Helland, Life beyond Distributed Transactions（CIDR 2007）：<http://cidrdb.org/cidr2007/papers/cidr07p15.pdf>
- Helland & Campbell, Building on Quicksand（CIDR 2009）：<https://arxiv.org/abs/0909.1788>
- Helland, Idempotence Is Not a Medical Condition（ACM Queue 2012）：<https://queue.acm.org/detail.cfm?id=2187821>
- Kleppmann, Turning the database inside-out（2014/2015）：<https://www.confluent.io/blog/turning-the-database-inside-out-with-apache-samza/>
- Fowler, Effectivity / Temporal Object / Bitemporal History：<https://martinfowler.com/eaaDev/Effectivity.html> / <https://martinfowler.com/eaaDev/TemporalObject.html> / <https://martinfowler.com/articles/bitemporal-history.html>
- Evans, Domain-Driven Design（2003）：《领域驱动设计》第 6 章「聚合」。
- CloudEvents v1.0：<https://github.com/cloudevents/spec/blob/main/cloudevents/spec.md>
- IETF draft-ietf-httpapi-idempotency-key-header：<https://datatracker.ietf.org/doc/html/draft-ietf-httpapi-idempotency-key-header>
- Stripe：Idempotent requests <https://docs.stripe.com/api/idempotent_requests> ；金额最小单位 <https://docs.stripe.com/currencies>
- Amazon Builders Library, Ensuring rollback safety：<https://aws.amazon.com/builders-library/ensuring-rollback-safety-during-deployments/>

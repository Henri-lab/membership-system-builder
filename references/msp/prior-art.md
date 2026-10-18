# MSP 成熟先例映射（prior art）

> 目的：MSP 不重新发明语义。每个对象/状态/操作尽量对齐成熟系统的公开语义，
> 只在没有先例的地方自创——目前**唯一**无先例的机制是个人收款码的「金额指纹」。
> 使用规则：做设计决策、移植参考实现、评审协议时对照本表；差异必须写进产出的"差分声明"。

## 1. 映射表

| MSP 概念 | 成熟先例 | 对齐方式与吸收内容 |
| --- | --- | --- |
| Product / Offer（kind） | Stripe Products/Prices；Kill Bill catalog（product/plan/phase） | `interval_count`、trial phase、套餐升级/降级语义 |
| Entitlement vs Membership | Kill Bill 的 **Entitlement（使用权）vs Subscription（财务义务）** 二分 | 判权只走 Entitlement；Membership 只承载计费周期 |
| 订阅生命周期 | Stripe Subscription 状态集 | `incomplete/incomplete_expired/trialing/active/past_due/unpaid/paused/canceled` + `cancel_at_period_end`；MSP 已收编 `trialing/active/past_due/paused/cancelled/expired` |
| 积分钱包 | **Lago Wallets**（`paid_credits/granted_credits` = 面值/赠送，wallet transactions = 流水） | 入账/消耗/退款事务语义、余额告警、自动充值 |
| 账本"唯一事实来源 + 只追加" | 银行流水；Stripe Balance Transactions；复式记账 | 积分用单式（ledger.md 策略 A/B）；资金可选复式（策略 C） |
| `balance_after` | 银行对账单 running balance | 物化优化，不变量仍以 `Σ delta` 为准 |
| 事务性发箱 + 至少一次 + 幂等消费 | **Transactional Outbox**（Chris Richardson, microservices.io）；inbox pattern；MassTransit / NServiceBus（.NET 一体实现）；Watermill（Go SQL publisher） | 事件与业务同事务；消费者按事件 id 去重；relay→MQ 拓扑与两种投递形态见 [../outbox.md](../outbox.md) §13 |
| 事件信封 | **CloudEvents v1.0**（CNCF，cloudevents.io） | 信封为其受限子集；`(id, source)` 唯一 ↔ 账本 `(source_event_id, ref)` 复合键 |
| `idempotency_key` | Stripe `Idempotency-Key`；IETF draft-ietf-httpapi-idempotency-key-header | key 与请求体绑定、处理中重试 409、key 保留期 |
| 金额整数最小单位 | Stripe 金额惯例；Fowler《PoEAA》Money 模式 | 持久化与运算只用整数分；算术封装在 Money 类型 |
| 退款状态机 | Stripe Refund：`pending/requires_action/succeeded/failed/canceled` | MSP 收编 `applied/processing/succeeded/failed/rejected/cancelled` |
| 续费提醒/催收 | Stripe smart retries；Recurly dunning sequences | 提醒契约：模板、窗口、去重键、渠道降级、退订 |
| API 演进 | Stripe 日期化 API 版本；Postel 定律 | 协议用日期版本 + 仅加法演进（extensions.md） |
| 金额指纹（**自创**） | 无直接先例；最接近银行转账"附言/参考号"匹配 | 因收款码无附言通道，只能用金额当信道——**必须**用最严不变量保护：租约独占（INV-27）、超时释放（OP-O5）、尾数不进退款（INV-20）、fixed 复用返回既有支付单 |
| 截图凭证 + OCR + 人工审核（确认策略 Tier 1） | 电商「转账后上传凭证」复核；银行对账单凭证核对；Stripe 补单 payment evidence | 流水号唯一绑定 + 歧义转人工 + 审核留痕（`payment-confirmation.md` §3，T-51~T-54） |
| 聚合服务商回调（确认策略 Tier 2） | 收钱吧/呗等聚合进件；托管式 onboarding（Stripe Connect 的弱化版） | webhook + 验签 + 幂等，核心契约同官方直连，无需自有 ICP 备案（视服务商） |
| 请求侧节流（v0.4） | Stripe 限流与 429/409 语义 | INV-31/32：并发意图上限 + 撞码退避熔断 |
| 人工转账回执（v0.4） | 银行转账回执；Stripe Refund 的渠道退款单号 | OP-R3 + INV-33：`(channel, transaction_no)` 唯一且不可变 |
| 数据保留与删除（v0.4） | PIPL / GDPR 删除权与保留期；财务凭证留存惯例 | INV-34：事实可留、标识可删（`data-retention.md`） |
| 续费提醒（v0.4） | Stripe smart retries；Recurly dunning | `reminder-contract.md`：窗口幂等键 + 退订隔离 |
| 账户合并（v0.4） | Auth0 account linking；银行账户合并的余额迁移 | OP-M2 + INV-36：段并集 + 账本 transfer，不可逆 |
| 部分退款（v0.3） | Stripe Credit Notes / Refund(amount) | `Refund.lines` + Σ ≤ paid + 按行回收（INV-28，T-39/40） |
| 试用与 proration（v0.3） | Stripe `trial_period_days` + `proration_behavior`；Kill Bill TRIAL phase | OP-T1/T2 试用与转正；OP-M1 三种 proration 行为（T-41~43） |
| 拒付/争议（v0.3） | Stripe Dispute 状态机 | OP-D1/D2 + 权益 `suspended` + 败诉账本追索（INV-29，T-44~46） |
| 税务发票（v0.3） | 快照哲学同 INV-2；税率引擎（Stripe Tax / Avalara）另立契约 | TaxSnapshot + Invoice + 红冲不改原票（T-47/48） |
| 多币种（v0.3） | Stripe `exchange_rate` | FxSnapshot + 原币退款 + 差额 adjust（INV-30，T-49/50） |

## 2. 决策时必查（顺序）

1. 该对象/状态/操作在 Stripe / Lago / Kill Bill 里叫什么、状态集是什么？
2. 参考实现的边界案例有哪些（proration、overdue、dispute、cancel_at_period_end）？逐条检查本设计是否覆盖或显式排除。
3. 差异声明：把"参考语义 vs 本实现语义"写进产出文档与符合性报告（差分用例）。

## 3. 差分用例模板

```markdown
| 主题 | 参考语义（出处） | 本实现语义 | 差异与风险 | 对应测试向量 |
| --- | --- | --- | --- | --- |
| 续期幂等 | Stripe 每次 Invoice 独立、不重复顺延 | 按 (principal, product, source) 幂等 | 无 | T-31 |
| 退款金额 | Stripe Refund.amount = charge 金额（不含内部尾数） | payable_amount，指纹尾数不计入 | 无 | T-36 |
```

## 4. 禁止事项

- 不要照抄参考实现的私有表结构/字段名——协议约束的是行为；
- 不要在协议正文粘贴参考文档原文——这里只放映射与指针；
- 新吸收的参考语义必须附带"出处 + 差分 + 测试向量"，三者缺一不可。

## 5. 设计判据文献（理论源头）

§1 的映射表管"产品语义对齐谁"；"为什么这样设计"的理论源头另见 [../master-craft.md](../master-craft.md)——
Helland 四个 I / 不可变账本 / 实体与活动、Kleppmann 派生数据、Fowler 段与双时序、Evans 聚合边界，
以及 CloudEvents / IETF / Stripe / AWS 工程实践，每条判据都对齐到 INV / OP / T 锚点。

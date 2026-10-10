# MSP 协议规范正文

> 本文使用 RFC 2119 语义：**必须（MUST）**、**禁止（MUST NOT）**、**应当（SHOULD）**、**可以（MAY）**。
> 协议面向"外部可观察行为"，不规定表名、字段名、进程拓扑、语言与中间件。

## 1. 通用约定

- **标识符**：所有对象有不可变、全局唯一、不透明（opaque）的引用 `*_ref`。调用方禁止解析其内部结构。
- **金额**：一律使用**整数最小货币单位**（如"分"）；禁止在任何持久化金额或金额运算中使用浮点数。
  `amount = { currency, minor_units }`，`currency` 为 ISO-4217 三字母。
- **时间**：所有持久化时间戳必须为 UTC；一切过期/时间窗判断以**服务端时间**为准，禁止信任调用方时间。
- **幂等键**：所有改变状态的操作（用户/管理员/内部回调）必须接受 `idempotency_key`
  （或天然唯一的业务键，如 `order_ref`、`payment_ref`）。同一键重复调用必须返回**相同结果**且不得重复产生副作用。
  语义对齐 IETF《The Idempotency-Key HTTP Header Field》（draft-ietf-httpapi-idempotency-key-header）：
  key 与请求体绑定（同 key 不同 payload 必须拒绝）、原请求仍在处理中的重试应当返回可重试错误
  （HTTP 层面为 409）、实现应当声明 key 的保留期并可清理过期 key。协议不强制 HTTP；
  绑定到 HTTP 时使用 `Idempotency-Key` 头。
- **扩展字段**：对象可携带 `meta`（键值映射）。扩展只能**新增** `meta` 字段、类型枚举值与事件类型，禁止改变既有字段语义。
- **资源门控**：任何受保护资源必须可被 `resource_ref` 唯一标识，用于访问检查（见 OP-E1）。

## 2. 对象模型（最小必需字段）

| 对象 | 必需字段 | 说明 |
| --- | --- | --- |
| Product | `product_ref, type, status, title` | `type` 为扩展点（membership / merch / gift / points_pack / …） |
| Offer | `offer_ref, product_ref, kind, price, status` | `kind ∈ {one_time, lifetime, subscription}`；subscription 必须有 `interval` |
| Order | `order_ref, principal, status, items[], totals, currency, expires_at, created_at` | 金额与条目为**下单时快照** |
| OrderItem | `offer_ref, product_ref, title_snapshot, quantity, unit_price, amount` | 下单后不可修改 |
| Payment | `payment_ref, order_ref, provider, channel, amount, status, expires_at` | `provider/channel` 为扩展点 |
| Entitlement | `entitlement_ref, principal, product_ref, source, status, starts_at, expires_at?` | **唯一判权事实来源**；`expires_at` 缺失 = 永久 |
| Membership | `membership_ref, principal, offer_ref, period_start, period_end, status, cancel_at_period_end?` | 订阅语义的**计费周期视图**（使用权见 Entitlement；二者分离对齐 Kill Bill 的 Entitlement vs Subscription）。`status ∈ {trialing, active, past_due, paused, cancelled, expired}` |
| PointsLedgerEntry | `entry_ref, principal, delta, kind, ref, balance_after, created_at` | 追加式账本；`kind` 为扩展点 |
| GiftInventory | `principal, product_ref, quantity` | 数量不得为负 |
| Shipment | `shipment_ref, order_ref, status, address_snapshot, carrier?, tracking_no?` | `address_snapshot` 必须为下单/发货时快照 |
| Refund | `refund_ref, order_ref, principal, amount, status, reason?` | 同一订单同时至多一个进行中退款 |

## 3. 状态机（允许的迁移是封闭集合）

**Order**

```
pending → paid → fulfilled
pending → cancelled        （用户取消）
pending → closed           （支付窗口超时，OP-O5）
paid|fulfilled → refunding
refunding → refunded       （退款成功）
refunding → paid|fulfilled （退款被拒/取消）
```

**Payment**

```
created → pending → succeeded | failed | expired
succeeded → refunded
```

**Refund**（对齐 Stripe Refund 状态集的语义，去掉不可达的中间态）

```
applied → processing → succeeded | failed
applied → succeeded                      （无外部资金通道的即时冲销，如人工转账后登记）
applied → rejected | cancelled
processing → cancelled
```

**Membership**（订阅计费视图；使用权由 Entitlement 判定）

```
trialing → active            （试用到期且已付费）
trialing → expired           （试用到期未付费）
active → past_due            （续费失败进入逾期）
past_due → active | cancelled | expired
active → paused → active
active|past_due → cancelled  （cancel_at_period_end 为期末取消；否则立即）
active → expired
```

**Entitlement**

```
active → expired（到期）
active → revoked（回收）
active → active（续期：仅修改 expires_at 与来源信息）
active → suspended（争议冻结，Disputes 等级）
suspended → active（争议获胜恢复）
suspended → revoked（争议败诉追索）
```

规则：

- 任何未列出的迁移**必须**被拒绝，返回 `INVALID_TRANSITION`，且不得产生副作用（INV-4）；
- 状态迁移**必须**是条件更新（"仅当当前状态为 X 才迁移到 Y"），并用影响行数/返回值判断是否已执行过；
- 终态（`fulfilled`、`cancelled`、`closed`、`refunded`、`expired`、`revoked`、`succeeded`、`failed`、`rejected`）到达后**禁止**再迁移（除 `fulfilled → refunding`）；
- 订单的 `refunding` 是 **MAY** 中间态：实现可以直接 `paid|fulfilled → refunded`，只要退款对象（Refund）自身状态机封闭；选择使用 `refunding` 的实现必须在退款终态时同步把订单终结。

## 4. 操作定义

> 每个操作给出：输入 / 前置 / 输出 / **副作用（必须原子）** / 错误 / 幂等要求。
> "副作用"一栏中标注 `[EVT]` 的表示必须同时写入事件（见 events.md）。

### 4.1 目录（管理员）

**OP-C1 `publishProduct`**

- 输入：`type, title, slug, meta?`
- 前置：`type` 在实现声明的类型集合内；`slug` 唯一。
- 输出：`product_ref`
- 副作用：写入商品（`status=draft|published`）。 `[EVT] product.published`（发布时）
- 错误：`INVALID_INPUT` / `CONFLICT`
- 幂等：以 `slug` 为天然键；重复发布同 `slug` 必须返回既有 `product_ref` 或 `CONFLICT`（实现需在文档中声明其一）。

**OP-C2 `publishOffer`**

- 输入：`product_ref, kind, price{currency,minor_units}, interval?, meta?`
- 前置：`product_ref` 存在且未归档；`kind=subscription ⇒ interval ∈ {month, year}`；`price ≥ 0`。
- 输出：`offer_ref`
- 副作用：写入报价。 `[EVT] offer.published`
- 错误：`INVALID_INPUT` / `NOT_FOUND`
- 幂等：以 `offer_ref` 或 `(product_ref, code)` 为键。

### 4.2 订单

**OP-O1 `createOrder`**

- 输入：`principal, items[{offer_ref, quantity}], address_ref?, idempotency_key`
- 前置：所有 `offer_ref` 可售；`quantity ≥ 1`；实体商品（type=merch）必须提供属于该 `principal` 的 `address_ref`。
- 输出：`order{order_ref, status=pending, totals, expires_at}`
- 副作用（必须同事务）：① 写入订单与条目**快照**（价格、标题、数量）；② 计算 `totals`（含运费/折扣）；③ 设定支付窗口 `expires_at`。 `[EVT] order.created`
- 错误：`INVALID_INPUT` / `NOT_FOUND` / `ADDRESS_REQUIRED`
- 幂等：同 `idempotency_key` 必须返回同一 `order_ref`，不得重复建单。

**OP-O2 `getOrder` / OP-O3 `listOrders`**

- 输入：`principal, order_ref`（或过滤条件）
- 输出：订单视图（含状态、金额、条目、时间）
- 副作用：无（只读）
- 错误：`NOT_FOUND` / `FORBIDDEN`（非本人订单必须返回 `FORBIDDEN`，不得泄露内容）
- 幂等：天然。

**OP-O4 `cancelOrder`**

- 输入：`principal, order_ref, idempotency_key`
- 前置：订单属于该 `principal` 且 `status=pending`。
- 输出：`order{status=cancelled}`
- 副作用（必须同事务）：① 订单 → `cancelled`；② 释放该订单**未支付**的结算占用（金额指纹等）；③ 作废未支付的支付单。 `[EVT] order.cancelled`
- 错误：`NOT_CANCELABLE` / `FORBIDDEN`
- 幂等：重复取消返回相同的 `cancelled` 状态。

**OP-O5 `closeExpiredOrders`**（内部/定时）

- 输入：无（或按过期时间过滤）
- 前置：订单 `status=pending` 且 `expires_at ≤ now()`（服务端时间）。
- 输出：受影响订单集合
- 副作用（逐单原子）：① 订单 `pending → closed`；② 释放该订单未支付的随机金额占用
  （实现可声明保留到 `expires_at + report_grace` 再释放，MAY，INV-8/27）；
  ③ 作废未支付的支付单；④ 写入事件。 `[EVT] order.closed`
- 错误：`INVALID_TRANSITION`（已迁移则跳过）
- 幂等：条件更新（`where status='pending'`），重复执行零副作用。

### 4.3 支付

**OP-P1 `createPaymentIntent`**

- 输入：`principal, order_ref, idempotency_key`
- 前置：订单属于该 `principal`、`status=pending` 且未过期；订单**不是**积分支付单。
- 输出：`payment{payment_ref, amount, expires_at, instructions}`，`instructions` 为**不透明**的支付指引
  （收款码 payload / 跳转 URL / 预支付 ID，形态由实现决定）。
- 副作用（必须同事务）：① 写入支付单（`pending`）；② 若使用金额指纹结算，登记唯一金额占用。 `[EVT] payment.intent_created`
- 错误：`NOT_PAYABLE` / `FORBIDDEN` / `AMOUNT_UNAVAILABLE`（指纹空间耗尽）
- 幂等：对同一 `order_ref` 的重复调用**应当**返回同一个未过期支付单，而不是新建多个。

**OP-P2 `reportSettlement`**（唯一允许把支付置成功的入口）

- 输入：`channel, amount, paid_at, provider_ref?, evidence{device, nonce, signature, timestamp}`
- 前置：**必须**验证来源真实性（签名/证书）与时间窗；**禁止**接受调用方直接声明"已支付"。
- 金额规则（使用金额指纹时）：命中金额 `settled = base + suffix`，必须满足
  ① 与某张未过期支付单的占用金额一致，且该金额码的租约未被其他支付单持有（INV-27）；
  ② `base` 等于订单 `payable_amount`。订单持久化 `paid_amount = base`，另存 `settled_amount`；
  退款金额只允许使用 `paid_amount`（INV-20）。
- 时间判定以 `paid_at`（支付发生时刻）为准，而非上报时刻：`paid_at ≤ expires_at` 即视为窗口内支付。
  实现可以声明上报宽容期 `report_grace`（默认建议 5–15 分钟，SHOULD）：窗口内支付、上报晚到但仍在
  grace 内 → 按命中履约；`paid_at` 晚于 `expires_at` 的到账**不得**自动履约，走 OP-P4 补单。
  注意：宽容期只放宽"上报晚到"，**不放宽"支付截止"**——不要通过延长 `expires_at` 来补偿监听延迟
  （那会推迟金额占用释放并让 UI 语义混乱）。
- 输出：`result ∈ {matched, unmatched, duplicate}` + `order_ref?`
- 副作用（必须同事务）：① 幂等记录通知本身（唯一键防重放）；
  ② 命中支付单 → `succeeded`、订单 `pending → paid`、结算占用结算（一次性模式消费/租约模式保留）；
  ③ 未命中 → 记录 `unmatched` 供对账，不得改动任何订单。 `[EVT] payment.succeeded`（命中时）
- 错误：`INVALID_SIGNATURE` / `TIMESTAMP_OUT_OF_WINDOW`（两者均不得留下副作用）
- 幂等：同一通知（同 nonce/provider_ref）重复上报必须返回 `duplicate` 且不重复履约。

**OP-P3 `queryPayment`**

- 输入：`payment_ref` 或 `order_ref`
- 输出：支付状态与 `provider_ref`
- 副作用：**可以**触发一次主动查单（用于回调丢失兜底），但不得绕过 OP-P2 的成功写入规则。

**OP-P4 `applyPaymentClaim`**（漏单兜底，用户自助）

- 输入：`principal, order_ref, channel, amount, paid_at?, transaction_no?, evidence[]`
- 前置：订单属于该 `principal` 且处于可补单状态。
- 输出：`claim{status=pending}`
- 副作用：写入待审凭证。不得直接发放权益。 `[EVT] payment.claim_applied`

**OP-P5 `reviewPaymentClaim`**（管理员）

- 输入：`operator, claim_ref, decision ∈ {approve, reject}, note?`
- 前置：凭证处于 `pending`。
- 输出：`claim{status}`
- 副作用（approve 时，必须同事务）：走与 OP-P2 命中分支**完全相同**的履约路径（订单 `paid` + 事件）。
- 错误：`NOT_REVIEWABLE`
- 幂等：重复审核返回终态，不重复履约。

### 4.4 权益

**OP-E1 `checkAccess`**

- 输入：`principal, resource_ref`
- 输出：`{allowed, reason, entitlement_ref?}`
- 副作用：无（只读）。**必须**实时判定（含到期），禁止只依赖批处理过期标记。
- 规则：判定**必须**仅依据 Entitlement（及协议显式允许的衍生视图），禁止从订单/支付推断访问权。

**OP-E2 `grantEntitlement`**（含续期）

- 输入：`principal, product_ref, source, duration?, idempotency_key`
- 前置：`duration` 为空表示永久；同一 `(principal, product_ref)` 至多一条活跃权益。
- 输出：`entitlement{status=active, expires_at?}` + `created: bool`
- 副作用（必须同事务）：① 新建或续期；② 写审计日志（actor + reason + 快照）。 `[EVT] entitlement.granted | entitlement.renewed`
- 续期规则：新到期时间 = `max(原到期时间, now) + duration`；原永久权益**禁止**被覆盖为限期。
- 幂等：同 `idempotency_key` 不重复叠加周期；**同一 `(principal, product_ref, source)` 的重复发放/续期
  也不得再次叠加**（INV-26）——事件重试/重放同一条 `order.paid` 必须得到相同到期时间。

**OP-E3 `revokeEntitlement`**

- 输入：`operator|system, principal, product_ref, reason`
- 输出：`entitlement{status=revoked}`
- 副作用：状态置 `revoked` + 审计日志。 `[EVT] entitlement.revoked`
- 幂等：重复回收返回相同终态。

**OP-E4 `listEntitlements`**

- 输入：`principal`；输出：活跃（及可选历史）权益列表；副作用：无。

### 4.5 积分（账本细节见 [ledger.md](ledger.md)）

**OP-N1 `creditPoints` / OP-N2 `debitPoints`**

- 输入：`principal, delta, kind, source, ref?, idempotency_key?`
- 前置：`delta ≠ 0`；出账必须**原子检查余额**（条件更新 / 行锁 / 冲突重试，任选其一），余额不得为负（除非显式声明透支策略）。
- 输出：`{balance_after, entry_ref}`
- 副作用（必须同事务）：① **追加**账本条目（含 `source/actor/balance_after`）；② 物化余额更新（采用策略 B 时）；
  ③ 审计信息。禁止 UPDATE/DELETE 历史条目。 `[EVT] points.credited | points.debited`
- 幂等：**结构化幂等键**（详见 ledger.md §4）：事件驱动用 `(source_event_id, ref)`、API 用 `(idempotency_key)`、
  补偿用 `(kind, ref)`；重复调用不得重复加/扣。**单列 `ref_id`/`event_id` 唯一不满足本协议。**

**OP-N3 `getPointsBalance` / OP-N4 `listPointsLedger`**

- 输入：`principal`；输出：余额与账本分页；副作用：无。

**OP-N5 `redeemWithPoints`**

- 输入：`principal, order_ref, idempotency_key`
- 前置：订单属于该 `principal`、`status=pending` 且未超过 `expires_at`（服务端时间）、结算方式为积分；余额充足。
- 输出：`order{status=paid}` + `points_moved`
- 副作用（必须同事务）：① 扣积分（走 OP-N2 语义）；② 订单 `pending → paid`；③ 写事件触发履约（与现金支付后的履约路径完全一致）。 `[EVT] order.paid`
- 错误：`INSUFFICIENT_POINTS` / `NOT_REDEEMABLE`
- 幂等：同 `idempotency_key` 只扣一次。

### 4.6 退款

**OP-R1 `applyRefund`**

- 输入：`principal, order_ref, reason?, idempotency_key`
- 前置：订单属于该 `principal` 且处于 `paid|fulfilled`；该订单没有进行中的退款。
- 输出：`refund{status=applied}`
- 副作用：写入工单（唯一约束防同一订单多工单）；订单可以迁移到 `refunding`（MAY，见 §3）。 `[EVT] refund.applied`
- 幂等：重复申请返回既有工单。

**OP-R2 `reviewRefund`**（管理员，通过即冲销）

- 输入：`operator, refund_ref, decision ∈ {approve, reject}, note?`
- 前置：工单处于 `applied`（或 `processing`，外部资金通道场景）。
- 输出：`refund{status=processing|succeeded|rejected}`
- 副作用（approve 时，**必须同事务**）：
  ① 回收本单发放的权益——**段回收**：仅回收本订单贡献的周期段
  （新到期 = 原到期 − 本单段长，下限为 `now()`；本单无段贡献则不变化），
  其他来源（更早订单、免费发放）贡献的时段**不得**被回收（INV-16）；
  ② 扣回本单赠送/充值的积分；③ 扣回本单入库且**尚未送出**的礼物（限量型同时回退计数）；
  ④ 若订单为积分支付，退回已扣积分；⑤ 作废未发货的周边发货单；
  ⑥ 该订单的支付单（若有）`succeeded → refunded`；
  ⑦ 订单 → `refunded`（或从 `refunding` 迁移），工单 → `succeeded`；⑧ 审计日志。 `[EVT] refund.succeeded`
- 失败策略：任一步不满足（礼物已送出、积分已花掉）→ **整体回滚**，工单保持 `applied`，
  返回 `MANUAL_REQUIRED`（禁止"退了钱但东西还在"）。 `[EVT] 无`
- 退款金额：MUST 等于订单 `payable_amount`；金额指纹的尾数不得计入（INV-20）。
- 幂等：重复审核返回终态；`reject` 后同订单**允许**重新申请（实现需在文档中声明该策略）。

**OP-R3 `attachTransferEvidence`**（管理员/运营，人工转账回执，v0.4）

- 输入：`operator, refund_ref, channel, transaction_no, amount_minor, paid_at, evidence_urls[], note?`
- 前置：工单存在且状态允许（`applied|processing|succeeded`）；`(channel, transaction_no)` 未被其它工单使用。
- 输出：`transfer_evidence{evidence_ref, status=attached}`
- 副作用：写入**不可变**回执记录 + 审计（actor + reason + 时间）。不改变退款工单的状态机。 `[EVT] refund.transfer_attached`
- 错误：`REFUND_NOT_FOUND` / `DUPLICATE_EVIDENCE` / `NOT_ATTACHABLE`
- 幂等：同 `(refund_ref, transaction_no)` 重复提交返回既有凭证记录，不新增。
- 资金通道差异：**个人收款码退款 MUST 在工单 `succeeded` 前/时关联至少一条转账回执**；
  官方 API 退款 SHOULD 用渠道退款单号（`provider_ref`）代替，并记录在工单上（INV-33）。

### 4.7 履约与发货（内部）

**OP-F1 `dispatchOnPaid`**（事件消费者）

- 输入：事件 `order.paid{order_ref}`
- 前置：订单 `status=paid`。
- 输出：履约结果
- 副作用（按 `product.type` 分派，必须幂等）：

  | type | 动作（`q` = 条目 quantity） |
  | --- | --- |
  | membership | `grantEntitlement`（周期 = `q × 一个报价周期`；实现也可声明 `q>1` 前置不满足）＋赠送积分 `q × points_per_period` |
  | points_pack | `creditPoints`（`q × (面值＋赠送)`） |
  | gift | 入库 `q` 件（限量型校验并递增已发售数 `q`） |
  | merch | 生成发货单（含地址快照，数量 `q`） |

  完成后订单 → `fulfilled`。
- 每个条目入账必须携带可区分条目的幂等键（INV-15）；同一事件的多次投递不得重复发放/入账。
- 幂等：重复消费不得重复发放（领取事件前检查信封 `event_id`，或依赖各子操作幂等键）。

**OP-S1 `shipOrder`**（管理员）

- 输入：`operator, shipment_ref, carrier, tracking_no`
- 前置：发货单处于 `pending|packed`。
- 输出：`shipment{status=shipped}`；副作用：写单号与时间、通知用户。 `[EVT] shipment.shipped`
- 幂等：重复提交相同单号返回相同状态。

## 5. 全局不变量（INV）

实现**必须**满足下列全部规则；这是"符合性判定"的核心。

- **INV-1（金额整数）** 任何持久化金额与金额运算必须为整数最小单位；禁止浮点。
- **INV-2（订单快照）** 订单金额与条目在下单后不可变；目录改价不得影响既有订单。
- **INV-3（单一判权源）** 访问判定必须仅依据权益（Entitlement）；禁止从订单/支付状态推断访问权。
- **INV-4（状态机封闭）** 未定义的状态迁移必须被拒绝且无副作用。
- **INV-5（条件迁移）** 所有状态迁移必须是条件更新，重复执行不得产生二次副作用。
- **INV-6（支付唯一写入口）** 只有经验证的结算上报（OP-P2）或审核通过的补单（OP-P5）可以把支付/订单置为已支付。
- **INV-7（结算通知幂等）** 同一结算通知重复到达必须判重且不重复履约。
- **INV-8（金额占用唯一与及时释放）** 使用金额指纹结算时，同一结算域内活跃金额占用全局唯一；
  占用在取消、超时关单（OP-O5）后必须及时释放，结算后按模式消费或保留。
- **INV-9（续期单调）** 续期 = `max(原到期, now) + 周期`；永久权益不得被限期覆盖。
- **INV-10（实时到期）** 权益到期必须实时生效（读路径判定），批处理只是补充。
- **INV-11（余额安全）** 积分/礼物余额不得为负（除非显式声明透支策略）；**扣减必须"检查与扣减原子化"**（条件更新 / 行锁 / 冲突重试，见 ledger.md C2），禁止"先读余额再写回"。
- **INV-12（余额同事务）** 余额更新与账本写入必须同一事务；禁止只改余额。
- **INV-13（账本唯一事实来源）** 账本是权威事实：任意事务边界满足 `balance == Σ delta`，余额必须可由账本重建（ledger.md L1/L4/B2）。
- **INV-14（账本不可变）** 账本只追加：退款/过期/纠错一律插入新条目；**禁止 UPDATE/DELETE 历史条目**（ledger.md L2）。
- **INV-15（结构化幂等键）** 事件驱动入账必须使用 `(source_event_id, ref)` 复合幂等键，且 `ref` 必须非空
  （存储引擎对 NULL 不去重时用 `NULLS NOT DISTINCT` 或等价约束兜底）；单列 `ref_id` / `event_id` 唯一**不满足**本协议（ledger.md §4）。
- **INV-16（退款完整性）** 退款成功必须伴随权益（按段回收）/积分/礼物/发货的同步回退；无法回退则退款不得成功。
- **INV-17（退款唯一工单）** 同一订单同时至多一个进行中退款工单。
- **INV-18（事件原子性）** 状态变更与事件写入必须原子（事务性发箱或等价机制）。
- **INV-19（至少一次 + 幂等消费）** 事件投递至少一次；消费者必须按 `event_id` 幂等，且不得依赖全局顺序。
- **INV-20（金额与币种一致）** 一单一种货币；资金变动必须区分 `payable_amount`（应付快照）与可选的
  `settled_amount`（实收，含指纹尾数），均为整数最小单位；退款金额必须等于 `payable_amount`。
- **INV-21（时钟权威）** 所有时间比较使用服务端 UTC 时间；不信任调用方时间。
- **INV-22（权限隔离）** 非本人资源访问必须返回 `FORBIDDEN` 且不得泄露内容，也不得产生任何状态变化。
- **INV-23（可对账）** 未匹配结算与失败事件必须可查询；实现必须提供对账入口（查询或报表）。
- **INV-24（审计）** 权益、积分、礼物、退款的每次变更必须有 actor + reason + 快照的审计记录。
- **INV-25（失败可重放）** 事件处理失败必须可重试；重试不得改变已达成的不变量。
- **INV-26（发放/续期按 source 幂等）** 权益发放/续期对同一 `(principal, product_ref, source)` 幂等：
  重复执行（事件重试/重放、重复请求）不得再次顺延或叠加周期（OP-E2）。
- **INV-27（结算码租约独占）** 使用金额指纹结算时，任一金额码同一时刻至多绑定一张未终结的支付单；
  到期/取消/结算后按 OP-O5 / OP-P2 规则释放或保留。
- **INV-28（退款上限）** 同一订单累计成功退款金额 ≤ `paid_amount`；部分退款按行回收，行内按金额占比折算段/积分/礼物。
- **INV-29（争议冻结范围）** 争议冻结只作用于该订单贡献的权益段；`won` 恢复、`lost` 追索都必须留审计与账本痕迹。
- **INV-30（跨币种快照）** 跨币种资金变动必须引用不可变汇率快照；退款币种 = 订单币种；汇率差额走 `adjust` 分录。
- **INV-31（支付意图并发上限）**（v0.4）同一 `principal` 对同一订单的重复/并发 `createPaymentIntent` 必须返回同一个未过期支付单；同一 `principal` 的活跃支付意图总数有实现声明的上限（默认 ≤5），超出返回 `TOO_MANY_ATTEMPTS` 且无副作用。
- **INV-32（撞码限速与告警）**（v0.4）金额指纹签发失败（`AMOUNT_UNAVAILABLE`）必须退避重试并记录告警；同一 `principal` 高频撞码失败触发熔断（快速失败 + 告警），不得无限空转。
- **INV-33（退款凭证唯一与不可变）**（v0.4）人工转账回执 `(channel, transaction_no)` 全局唯一、只追加不可变，同一回执只能绑定一个退款工单；`succeeded` 的退款必须能回答"钱退到哪、谁操作、回执是什么"——个人码 MUST 有转账回执，官方 API SHOULD 有渠道退款单号。
- **INV-34（个人信息与事实分离）**（v0.4）不可变事实（账本/事件/支付与退款凭证）不得嵌入可识别个人信息；个人信息独立存储且支持掩码/删除；删除个人信息或清零余额（走负向条目）不得破坏账本可重建性（INV-13/14）。

## 6. 错误模型（最小集合）

| 代码 | 语义 | 约束 |
| --- | --- | --- |
| `INVALID_INPUT` | 参数不合法 | 无副作用 |
| `NOT_FOUND` | 对象不存在 | 不得泄露存在性之外的信息 |
| `FORBIDDEN` | 非本人资源 | 无副作用 |
| `CONFLICT` | 唯一性冲突 | 无副作用 |
| `INVALID_TRANSITION` | 状态机不允许 | 无副作用 |
| `NOT_PAYABLE` / `NOT_CANCELABLE` / `NOT_REDEEMABLE` / `NOT_REVIEWABLE` | 前置不满足 | 无副作用 |
| `INSUFFICIENT_POINTS` / `INSUFFICIENT_BALANCE` | 余额不足 | 无副作用 |
| `AMOUNT_UNAVAILABLE` | 金额指纹空间耗尽 | 无副作用 |
| `TOO_MANY_ATTEMPTS` | 活跃支付意图超上限 / 高频撞码熔断 | 无副作用 |
| `INVALID_SIGNATURE` / `TIMESTAMP_OUT_OF_WINDOW` | 回调不可信 | 无副作用 |
| `MANUAL_REQUIRED` | 需人工处理（退款冲销失败等） | 仅记录状态，不产生资金副作用 |
| `REFUND_EXCEEDED` / `TRIAL_USED` / `NOT_TRIALABLE` / `DISPUTE_EXISTS` / `NOT_DISPUTABLE` | 前置不满足（v0.3） | 无副作用 |

## 7. 并发与一致性要求

- **MUST** 保证同一订单的并发支付上报只有一个成功（数据库唯一约束或行锁）；
- **MUST** 保证同一权益的并发发放/续期不会产生两条活跃记录；
- **MUST** 保证限量型礼物与积分扣减在并发下不超卖、不透支；
- **MUST** 保证金额指纹的租约独占（INV-27）与超时释放（OP-O5）；
- **SHOULD** 对高频只读（目录）提供缓存，但缓存失效不得影响不变量；
- **SHOULD** 对外部结算与事件处理提供幂等性测试（见 conformance.md）。

## 8. v0.3 主题（2026-10-10，按加法原则追加）

> 本节在既有对象/状态机/操作之上**只做加法**；全部既有语义不变。

### 8.1 部分退款（Core 追加）

追加对象字段：

- `Refund.lines?`：`[{order_item_ref, amount_minor, reason?}]`，`amount = Σ lines.amount_minor`；
- 未给 `lines` 视为对"剩余可退金额"整单退款。

追加状态迁移（Order）：

```
paid|fulfilled → refunding → partially_refunded
partially_refunded → refunding → refunded | partially_refunded
```

OP-R1 修改：

- 前置增加：订单处于 `paid|fulfilled|partially_refunded`；
  `Σ lines.amount_minor ≤ remaining_refundable = paid_amount − Σ(已成功退款)`；
- 错误增加 `REFUND_EXCEEDED`。

OP-R2 修改（approve 的回收按行执行）：

- 每条 `line` 对该订单条目按金额占比折算：权益段缩短 = 本单段长 × `line.amount / item.amount`
  （时长按秒，舍入方式实现声明）；积分/礼物按行扣回；
- 订单 → `partially_refunded`（剩余可退 > 0）或 `refunded`（剩余可退 = 0）；
- 不变量：INV-28（跨多笔工单恒成立）。

### 8.2 试用与 proration（Subscriptions 追加）

**OP-T1 `startTrial`**

- 输入：`principal, offer_ref, idempotency_key`
- 前置：`offer.kind=subscription` 且 `trial_days > 0`；同一 `(principal, product_ref)` 未使用过试用
  （实现可放宽并在文档声明）。
- 输出：`entitlement{expires_at = now + trial_days}` + `membership{status=trialing}`
- 副作用：发权益（`source=trial`）+ 审计。 `[EVT] subscription.trial_started`
- 错误：`TRIAL_USED` / `NOT_TRIALABLE`
- 幂等：同 key 不重复发放。

**OP-T2 `convertTrial`**（试用转正）

- 输入：`principal, offer_ref, idempotency_key`（等价于对该报价正常下单支付）
- 副作用：与普通订单支付完全一致（OP-F1）；Membership `trialing → active`；
  权益续期 = `max(原到期, now) + 周期`——**剩余试用天数不丢**（INV-9 的推广）。
- 到期：`trialing` 且 `expires_at ≤ now()` 且未转正 → Membership `expired`（可由关单/提醒 worker 执行）。

**OP-M1 `changeOffer`**（升级/降级，MAY）

- 输入：`principal, membership_ref, new_offer_ref, proration_behavior ∈ {none, create_prorations, always_invoice}, idempotency_key`
- 前置：Membership `active`；新旧报价同 product、同 `kind=subscription`。
- 计算：`unused_value = 已付金额 × 剩余时长 / 总时长`；`delta = 新报价价格 − unused_value`。
- 副作用：`none` → 放弃剩余价值，换报价重算段（新到期 = now + 新周期）；
  `create_prorations` → `delta > 0` 记入下期应付（生成待支付补差订单）、`delta < 0` 记入账本贷项（只追加）；
  `always_invoice` → 立即生成补差订单。 `[EVT] subscription.offer_changed`
- 约束：补差**必须**走订单/账本，禁止直接改权益时长；四舍五入规则实现声明。

### 8.3 拒付 / 争议（新等级 Disputes）

追加对象：

| Dispute | `dispute_ref, order_ref, payment_ref?, principal, status, reason, amount, opened_at, resolved_at?` | 一个支付单至多一个进行中争议 |

追加状态机：

```
Dispute: opened → needs_response → under_review → won | lost
         opened → lost          （主动接受/未回应）
```

**OP-D1 `openDispute`**（支付方/渠道上报争议）

- 输入：`order_ref|payment_ref, reason, amount, evidence?`
- 前置：存在已成功支付；同一支付单无进行中争议。
- 副作用：写 Dispute(`opened`)；**冻结该订单来源的权益段**（`active → suspended`，仅本单贡献，INV-29）。 `[EVT] dispute.opened`
- 错误：`DISPUTE_EXISTS` / `NOT_DISPUTABLE`

**OP-D2 `resolveDispute`**（管理员/渠道结果）

- 输入：`operator|channel, dispute_ref, outcome ∈ {won, lost}, note?`
- 副作用：`won` → 解冻恢复（`suspended → active`）+ 审计；
  `lost` → 权益段 `suspended → revoked` + 账本插入负向分录（`kind=chargeback`，记录追索）+ 审计；
  Dispute 终态化。 `[EVT] dispute.won | dispute.lost`
- 资金侧：个人码阶段只记录与人工追索，协议不要求自动转账。
- 幂等：重复决议返回终态。

### 8.4 税务发票（新等级 Invoicing）

追加对象：

| TaxSnapshot | `tax_ref?, currency, lines[{label, rate, amount_minor}], total_tax_minor` | 下单时快照（受 INV-2 保护） |
| Invoice | `invoice_ref, order_ref, principal, invoice_no, status, lines[], total_minor, issued_at?, voided_at?` | `status ∈ {draft, issued, void, red}` |

**OP-I1 `issueInvoice`**

- 前置：订单 `paid|fulfilled|refunded`；`invoice_no` 唯一。
- 副作用：开具发票（含税率/税额快照）。 `[EVT] invoice.issued`
- 约束：税率变更不得影响已开票（快照）；发票金额 = 订单应付（含税规则由实现声明）。

**OP-I2 `redInvoice`**（红冲）

- 前置：原发票 `issued`。
- 副作用：新增一张 `status=red` 的负向发票（引用原 `invoice_no`）；**禁止**修改原发票。 `[EVT] invoice.red`

**明确不做**：税务计算引擎、管辖地/税率来源、合规归档——按 extensions.md §4 另立契约；
本协议只固定"税率快照 + 红冲不改原票"两个资金安全点。

### 8.5 多币种（新等级 MultiCurrency）

追加对象：

| FxSnapshot | `fx_ref, from_currency, to_currency, rate, captured_at, source` | 汇率快照，不可变 |

规则：

- 一单一种货币不变（INV-20）；任何跨币种结算/退款**必须**携带并持久化 `fx_snapshot`；
- 折算一律按快照汇率，禁止事后用实时汇率重算；退款一律按订单原币（快照只是换算口径）；
- 汇率漂移产生的差额 → `adjust` 分录（只追加，禁止改历史）。

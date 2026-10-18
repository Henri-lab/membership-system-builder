# MSP 事件契约

> 事件是协议的一部分：只要实现声明"支持某类型事件"，就必须满足下面的信封、语义与幂等要求。
> 传输方式（数据库 outbox、消息队列、HTTP 回调）由实现决定，**不改变契约**。

## 1. 事件信封（MUST）

信封是 **CloudEvents v1.0（CNCF，cloudevents.io）的受限子集**；字段名沿用 CloudEvents，
`version` 与 `aggregate` 为 MSP 扩展属性：

```json
{
  "specversion": "1.0",
  "id": "uuid",
  "source": "settlement/domain-uri",
  "type": "order.paid",
  "version": 1,
  "time": "2026-10-10T06:34:57Z",
  "subject": "order_ref",
  "datacontenttype": "application/json",
  "aggregate": { "type": "order", "ref": "order_ref" },
  "data": { }
}
```

| 本协议字段 | CloudEvents 属性 | 语义 |
| --- | --- | --- |
| `id`（原 `event_id`） | `id` | 与 `source` 组合后全局唯一；消费者以此做幂等键（INV-19） |
| `source` | `source` | 事件生产者/结算域的 URI；**必填** |
| `specversion` | `specversion` | 固定 `1.0` |
| `type` | `type` | `<aggregate>.<action>`；扩展类型带命名空间前缀（如 `x-campaign.rewarded`） |
| `version` | （扩展属性） | 事件类型语义版本；变化时递增，只允许向后兼容的加法 |
| `time`（原 `occurred_at`） | `time` | UTC，事件发生时刻（非投递时刻） |
| `subject`（原 `aggregate.ref`） | `subject` | 产生事件的聚合根引用 |
| `aggregate` | （扩展属性） | 聚合类型 + 引用，兼容旧消费者 |
| `datacontenttype` | `datacontenttype` | 默认 `application/json` |
| `data` | `data` | 类型特有负载，见第 2 节 |

字段规则：

- `id + source`：全局唯一、不可重复；事件驱动的账本幂等键 `(source_event_id, ref)` 中的
  `source_event_id` 即本 `id`——复合唯一对齐 CloudEvents 的 `(id, source)` 唯一性（INV-15）。
- 消费者**必须**忽略未知字段与未知事件类型（前向兼容）。

## 2. 必需事件（实现按声明范围提供）

### 2.1 `order.paid`（Core 必选）

```json
{ "order_ref": "…", "principal": "…", "paid_amount": {"currency":"CNY","minor_units":19900},
  "items": [{"offer_ref":"…","product_ref":"…","quantity":1}], "paid_at": "…" }
```

- 触发时机：支付成功且订单已迁移到 `paid` 的**同一事务**内（INV-18）。
- 消费者义务：`dispatchOnPaid`（OP-F1）必须幂等；重复消费不得重复发放。
- 字段级别：`order_ref` MUST；`principal/paid_amount/items/paid_at` SHOULD——消费者**必须**
  以权威状态（订单/权益/账本）为准，事件负载只作通知与快速分派（允许"引用式负载"）。
  金额字段与 INV-20 一致：`paid_amount` 为应付金额（不含指纹尾数）；存在尾数时另带 `settled_amount`。

### 2.2 `payment.succeeded`（Core 必选）

```json
{ "payment_ref": "…", "order_ref": "…", "amount": {"currency":"CNY","minor_units":19901},
  "channel": "wechat", "provider_ref": "…", "paid_at": "…" }
```

### 2.3 `entitlement.granted` / `entitlement.renewed` / `entitlement.revoked`

```json
{ "entitlement_ref": "…", "principal": "…", "product_ref": "…",
  "source": "order:…", "starts_at": "…", "expires_at": "…|null" }
```

- `granted` 与 `renewed` 必须能区分（首次 vs 顺延）；`expires_at=null` 表示永久。

### 2.4 `refund.applied` / `refund.succeeded`

```json
{ "refund_ref": "…", "order_ref": "…", "amount": {"currency":"CNY","minor_units":9900},
  "lines": [{"order_item_ref":"…","amount_minor":9900}], "reason": "…", "completed_at": "…" }
```

- `amount` 必须等于订单 `payable_amount`（不含金额指纹尾数，INV-20）。
- 部分退款（v0.3）时 `lines` 必填；`amount = Σ lines.amount_minor`（INV-28）。

### 2.5 其它推荐事件

| 事件 | 触发时机 | 关键字段 |
| --- | --- | --- |
| `order.created` | 下单成功 | `order_ref, principal, totals, expires_at` |
| `order.cancelled` | 用户取消/超时关单 | `order_ref, reason` |
| `payment.intent_created` | 支付意图签发 | `payment_ref, order_ref, expires_at` |
| `payment.expired` | 支付窗口过期 | `payment_ref, order_ref` |
| `points.credited` / `points.debited` | 积分变动 | `principal, delta, kind, balance_after` |
| `shipment.created` / `shipment.shipped` | 周边履约 | `shipment_ref, order_ref, status` |
| `payment.claim_applied` | 用户提交漏单凭证 | `claim_ref, order_ref` |
| `refund.transfer_attached` | 退款工单关联人工转账回执（v0.4） | `refund_ref, channel, transaction_no, amount_minor, paid_at` |
| `reminder.sent` / `reminder.skipped` | 到期/续费提醒发送或跳过（v0.4） | `principal, entitlement_ref, reminder_key, window_start, reason` |
| `account.merged` | 账户合并完成（v0.4） | `source_principal, target_principal, mapping` |

### 2.6 `dispute.opened` / `dispute.won` / `dispute.lost`（Disputes 等级）

```json
{ "dispute_ref": "…", "order_ref": "…", "payment_ref": "…|null", "reason": "…",
  "amount": {"currency":"CNY","minor_units":19900}, "outcome": "won|lost" }
```

### 2.7 `invoice.issued` / `invoice.red`（Invoicing 等级）

```json
{ "invoice_ref": "…", "order_ref": "…", "invoice_no": "…", "status": "issued|red",
  "original_invoice_no": "…|null", "total_minor": 19900 }
```

### 2.8 `subscription.trial_started` / `subscription.offer_changed`（Subscriptions 等级）

```json
{ "membership_ref": "…", "principal": "…", "offer_ref": "…", "trial_days": 7 }
```

```json
{ "membership_ref": "…", "old_offer_ref": "…", "new_offer_ref": "…",
  "proration_behavior": "create_prorations", "delta_minor": -1200 }
```

## 3. 投递与消费语义（MUST）

> 实现机制（事务性发箱、SKIP LOCKED 领取、死信闭环、吞吐观测）见 [../outbox.md](../outbox.md)；本节只定行为。

1. **至少一次**：发布方必须保证事件最终被投递（失败重试 + 退避）；
2. **幂等消费**：消费者必须按 `event_id` 去重（例如收件箱表 + 唯一约束）；
3. **禁止依赖顺序**：不得假设跨聚合、跨类型事件的全局或局部顺序；需要顺序时以状态机条件更新实现；
4. **原子发布**：状态变更与事件写入必须同事务（INV-18）；
5. **可重放**：历史事件必须可按 `event_id` 手动重放，且重放不破坏不变量（INV-25）；
6. **可观测**：失败事件必须可查询（含重试次数与最后错误）；达到重试上限后的处置策略（继续退避 / 转人工）必须写进实现文档。
7. **信封互操作**：信封对齐 CloudEvents v1.0 的受限子集（见第 1 节映射表）；`(id, source)` 全局唯一。

## 4. 事件与操作的关系（可追溯性）

| 操作 | 必须产生的事件 |
| --- | --- |
| OP-O1 `createOrder` | `order.created` |
| OP-O4 `cancelOrder` | `order.cancelled` |
| OP-O5 `closeExpiredOrders` | `order.closed` |
| OP-P1 `createPaymentIntent` | `payment.intent_created` |
| OP-P2 `reportSettlement`（命中） | `payment.succeeded` + `order.paid` |
| OP-P5 `reviewPaymentClaim`（通过） | `order.paid` |
| OP-E2 `grantEntitlement` | `entitlement.granted`（首次）/ `entitlement.renewed`（顺延） |
| OP-E3 `revokeEntitlement` | `entitlement.revoked` |
| OP-N1/N2 积分变动 | `points.credited` / `points.debited` |
| OP-N5 `redeemWithPoints` | `order.paid` |
| OP-R1 `applyRefund` | `refund.applied` |
| OP-R2 `reviewRefund`（通过） | `refund.succeeded` |
| OP-R3 `attachTransferEvidence` | `refund.transfer_attached` |
| OP-M2 `mergePrincipals` | `account.merged` |
| OP-S1 `shipOrder` | `shipment.shipped` |
| OP-T1 `startTrial` | `subscription.trial_started` |
| OP-M1 `changeOffer` | `subscription.offer_changed` |
| OP-D1 `openDispute` | `dispute.opened` |
| OP-D2 `resolveDispute` | `dispute.won` / `dispute.lost` |
| OP-I1 `issueInvoice` | `invoice.issued` |
| OP-I2 `redInvoice` | `invoice.red` |

## 5. 扩展与兼容

- 新增事件类型必须使用命名空间（`x-…`）或与既有类型无冲突的新聚合名；
- 事件负载只允许**新增字段**；消费者必须忽略未知字段（前向兼容）；
- 删除或改变字段语义 = 新 `version` + 新类型（禁止原地改义）。

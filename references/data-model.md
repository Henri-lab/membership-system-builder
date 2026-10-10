# 数据模型目录（可按业务范围裁剪）

## 约定

- 金额 `bigint`（分）；时间 `timestamptz`（UTC）；主键 `uuid default gen_random_uuid()`；事件表 `bigserial`；
- 状态 `text + check`；`updated_at` 由触发器维护；
- 唯一索引与部分索引是**业务不变量**的载体，不要省略。

## 身份

| 表 | 关键字段 | 关键约束 |
| --- | --- | --- |
| users | phone/email 至少一个、password_hash、status | `unique(phone)`, `unique(email)` |
| sessions | user_id、refresh_token_hash、expires_at、revoked_at | 用于登出与吊销 |
| admin_users | user_id、role | `role in (super_admin, operator, support, finance, content)` |

## 目录

| 表 | 关键字段 | 关键约束 |
| --- | --- | --- |
| products | type、title、slug、status、creator_id(可选) | `type in (membership, merch, gift, points_pack, …)`；`unique(slug)` |
| offers | product_id、kind、price_cents、interval、meta | `kind in (one_time, lifetime, subscription)`；订阅必须有 interval |
| posts（内容） | creator_id、access jsonb、status | `access.mode in (public, members, product)` |

`offers.meta` 的约定（用 JSONB 承载扩展，不动表结构）：

```json
{"amount_mode":"fixed"}
{"points_per_period":100}
{"points":1000,"bonus":100}
{"payment_mode":"points","points_price":300}
```

## 交易

| 表 | 关键字段 | 关键约束 |
| --- | --- | --- |
| orders | order_no、user_id、status、金额快照、expires_at | 状态机见架构文档；`unique(order_no)` |
| order_items | order_id、offer_id、product_id、title_snapshot、数量、单价、`variant_snapshot` | 下单即快照，防篡改 |

## 支付

| 表 | 关键字段 | 关键约束 |
| --- | --- | --- |
| payments | order_id、channel、out_trade_no、amount_cents、amount_code、status | `unique(out_trade_no)` |
| payment_amount_reservations | amount_cents、mode、user_id、offer_id、suffix_cents、price_cents、status | `unique(amount_cents) where status='active'` |
| payment_notifications | provider、nonce、amount_cents、status、matched_* | `unique(provider, nonce)` 防重放 |
| payment_claims | order_id、user_id、金额、凭证、status | 漏单兜底工单 |
| refunds | refund_no、order_id、amount_cents、status、review_note | `unique(order_id) where status in ('applied','approved','processing')` |
| refund_transfer_evidences | refund_id、channel、transaction_no、amount_cents、paid_at、evidence_urls、reviewer | `unique(channel, transaction_no)` 防回执复用；只追加不可变 |

## 权益

| 表 | 关键字段 | 关键约束 |
| --- | --- | --- |
| entitlements | user_id、product_id、source_type、scope、starts_at、expires_at、status | `unique(user_id, product_id) where status='active'` |
| entitlement_logs | action（grant/renew/expire/revoke/extend）、actor、快照 | 审计 |
| memberships | user_id、offer_id、period_start/end、auto_renew | 收款码阶段 `auto_renew=false` |
| entitlement_reminders | (entitlement_id, template_key) | 主键去重，多实例安全 |

续期算法（写进 SQL，不要在应用层拼时间）：

```sql
-- 续期：在「原到期时间与当前时间的较晚者」上顺延，提前续费不丢天数；永久权益不被覆盖
expires_at = case
  when 周期 is null then null
  when entitlements.expires_at is null then null
  else greatest(entitlements.expires_at, now()) + 周期
end
```

## 积分

| 表 | 关键字段 | 关键约束 |
| --- | --- | --- |
| points_balances | user_id、balance | `check(balance >= 0)` |
| points_ledger | delta、kind、ref_type/ref_id、event_id、balance_after | `unique(event_id, ref_id) where event_id is not null` |

kind：`recharge / subscription_bonus / gift_spend / redeem / refund / adjust / expire`。

## 礼物

| 表 | 关键字段 | 关键约束 |
| --- | --- | --- |
| gifts | product_id、gift_type、limited_total、issued_count | `gift_type in (consumable, collectible)` |
| gift_inventory | user_id、product_id、balance | 主键 `(user_id, product_id)` |
| gift_ledger | delta、kind(purchase/send/refund/adjust)、event_id | `unique(event_id, product_id) where event_id is not null` |
| gift_sends | sender、creator、product、quantity、value_cents | 榜单与偶像侧收藏的来源 |
| gift_leaderboard | creator_id、scope(all/month)、period_start、total_value_cents | 主键 `(creator_id, scope, period_start)` |

## 收货与发货

| 表 | 关键字段 | 关键约束 |
| --- | --- | --- |
| addresses | user_id、收件人、手机、省市区、详细地址、is_default | 必须属于本人 |
| shipments | order_id、creator_id、status、carrier、tracking_no、`address_snapshot` | 每单一张；状态 pending→shipped→delivered |

## 基础设施

| 表 | 关键字段 | 关键约束 |
| --- | --- | --- |
| outbox_events | aggregate_type/id、event_type、payload、status、retry_count、available_at | 部分索引 `(available_at) where status in ('pending','failed')` |
| notifications | user_id、channel(inapp/email/sms/wechat)、template_key、payload、status | 按订单去重的部分唯一索引 |
| events | user_id(可空)、type、payload、occurred_at | 行为埋点，只追加 |

## 迁移纪律

- 一个目录、按序号命名（`0001_init.up.sql`）、按文件名排序执行；
- 每个迁移在**单事务**中执行，成功后写 `schema_migrations`，失败整体回滚；
- 已应用的迁移文件不修改（改动一律新增序号）；
- 本地与服务端同一套迁移，服务启动时自动执行（幂等）。

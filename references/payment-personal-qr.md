# 个人收款码支付链路（personal_qr）

适用：没有商户号/营业执照，用个人微信或支付宝收款码收款；到账没有订单号，只能靠金额区分。

## 1. 金额指纹协议

在订单应付金额（基础价，分）上加一个**唯一分位**：

```
实付金额 = 基础价 + 唯一后缀（1..maxSuffix 分，默认 1..99）
199.00 元 → 199.01 … 199.99 元
```

占用表（关键约束在唯一索引）：

```sql
create table payment_amount_reservations (
  id            uuid primary key default gen_random_uuid(),
  amount_cents  bigint not null,
  mode          text not null check (mode in ('random','fixed')),
  user_id       uuid references users(id),
  offer_id      uuid references offers(id),
  order_id      uuid references orders(id),
  payment_id    uuid references payments(id),
  suffix_cents  int,
  price_cents   bigint,           -- 签发时基础价，用于识别改价后的僵尸码
  status        text not null default 'active'
                check (status in ('active','consumed','released','expired')),
  expires_at    timestamptz,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);
create unique index uq_amount_active on payment_amount_reservations (amount_cents)
  where status = 'active';
```

## 2. 两种模式

| 模式 | 租期 | 用途 | 结算行为 |
| --- | --- | --- | --- |
| `random` | 随订单短租（默认 15 分钟） | 一次性购买、礼物、积分包、周边 | 匹配后置 `consumed`，用完即弃 |
| `fixed` | 按「用户 × 报价」长租（默认 180 天） | 订阅/会员续费 | 匹配后**保持 active**、只解绑订单与支付单——续费复用同一个数字 |

决策顺序（唯一决策点）：报价级 `offers.meta.amount_mode` > 全局开关 > 按报价类型推导（订阅→fixed，其余→random）。

续费时若发现基础价变化或租约过期：作废旧固定金额，重新签发。

## 3. 签发算法（并发安全）

```
循环最多 N 次（N=20）：
  事务：
    读取 [base+1, base+maxSuffix] 区间内 active 且未过期的占用（FOR UPDATE）
    从 1..maxSuffix 取第一个未占用后缀
    插入 payments(pending) + payment_amount_reservations(active)
  冲突（唯一索引 23505）→ 重试
仍失败 → 返回「金额繁忙，请稍后重试」
```

固定模式额外步骤：先查该 `(user_id, offer_id)` 是否已有活跃固定金额；有且价格一致且未过期 → 复用（延长租期 + 绑定新支付单）；否则作废重签。

## 4. 监听端与到账上报

监听端（另一台手机/自动化）检测到到账后调用服务端内部接口：

```
POST /internal/payment-notifications
{
  "device_id": "android-01",
  "channel": "wechat",
  "amount_cents": 19901,
  "paid_at": "2026-10-10T12:00:00Z",
  "nonce": "<随机串>",
  "timestamp": 1791614400,
  "signature": "<HMAC-SHA256>"
}
```

签名串（固定格式，两端一致）：

```
deviceID|channel|amountCents|paidAtUnix|nonce|timestamp
```

服务端校验：HMAC 相等（固定时间比较）→ 时间戳漂移 ≤ ±5 分钟 → `(provider, nonce)` 唯一约束防重放。

## 5. 匹配事务（核心）

```
事务：
  1. 插入 payment_notifications（唯一键冲突 → duplicate，直接返回）
  2. 按 amount_code + channel 找 pending 且未过期的支付单（FOR UPDATE）
     找不到 → 通知保持 unmatched，提交后返回 unmatched（人工/告警处理）
  3. 支付单置 succeeded、写 paid_at
  4. 订单置 paid、写 paid_amount_cents（条件更新，仅在 pending 时生效）
  5. 结算金额占用：
       random → status='consumed'
       fixed  → 保持 'active'，order_id/payment_id 置空（回到「用户×报价」长租态）
     并释放同一订单下其它 random 占用
  6. 写 outbox：order.paid
  7. 通知置 matched（回填 payment/order 外键）
提交
```

## 6. 漏单兜底（自助举证）

监听端挂机会漏单，纯自动匹配不可靠。提供：

```
POST /api/orders/{id}/refund-style claim:
  { channel, amount_cents, paid_at, transaction_no, evidence_urls[] }
```

用户提交后进入 `payment_claims(pending)`；后台审核通过 → 走与自动匹配相同的履约路径（幂等由「订单状态条件更新 + 事件幂等」保证）。

## 7. 对账

- 每日核对：`payments(scope)` 与订单表按 `order_no/外部单号` 对账；
- `payment_notifications` 中 `unmatched` 记录必须有人看（告警或后台列表）；
- 固定金额的僵尸码（改价后未清理）要定期扫描 `price_cents != 当前报价` 的记录。

## 8. 专属坑（都在真实项目踩过）

1. **`ON CONFLICT` 与部分唯一索引**：冲突目标必须带同样的谓词
   （`on conflict (event_id, ref_id) where event_id is not null do nothing`），否则报 `42P10`。
2. **跨系统撞码**：两个系统监听同一个收款账户时，同一金额可能被两边同时匹配 → 必须使用不同账户/渠道，或分区金额后缀空间。
3. **固定金额不能"消费"**：续费要复用同一数字，匹配后必须保持 `active`。
4. **取消/超时要释放占用**：否则可用金额空间随时间枯竭。
5. **改价产生僵尸码**：用 `price_cents` 快照识别并作废。
6. **金额必须含唯一分位**：只按整数元匹配会大面积冲突。
7. **退款不是技术退款**：个人收款码没有 API 退款，退款 = 人工转账 + 工单冲销（见 architecture.md 的退款不变量）。

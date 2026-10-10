# 续费提醒与通知契约（reminder contract）

> 适用分支：`inapp_reminder` / `+dunning`。个人码阶段没有自动扣款——提醒语义是
> "通知用户续费"，不是催收扣款；催收（dunning）在官方自动续费场景才有意义。

## 1. 语义分层

| 档位 | 名称 | 触发 | 参考语义 |
| --- | --- | --- | --- |
| 提醒 | 到期提醒（`inapp_reminder`） | 权益到期前窗口（默认 7/3/1 天）告知"即将到期，续费请下单" | 站内/邮件到期通知 |
| 催收 | 多档催收（`+dunning`） | 官方自动续费失败后的重试序列 | Stripe smart retries；Recurly dunning |

## 2. 触发与去重

- 触发对象：`entitlements` 中 `status=active`、位于到期前窗口内的权益；
  已退订提醒或本窗口已发送 → 跳过；
- 幂等键：`(principal, entitlement_ref, reminder_key, window_start)`——
  定时任务重跑、多实例并发只发一次（与 INV-15 的复合幂等键同构）；
- 时间判定一律服务端 UTC（INV-21）。

## 3. 渠道与降级

| 优先级 | 渠道 | 条件 |
| --- | --- | --- |
| 1 | 站内信 | 必选，无额外条件 |
| 2 | 邮件 | 已绑定并验证邮箱 |
| 3 | 渠道推送（微信服务号等） | 用户已授权 |

降级链：高优先级失败/不可用 → 下一档；全部失败 → 记录失败事件供重试，**不得静默丢弃**。

## 4. 退订隔离（关键不变量）

- 退订提醒（`unsubscribeReminders`）只影响提醒渠道，**不得**影响订阅状态、续费顺延、权益判权（INV-35）；
- 退订记录 `(principal, channel)` 唯一，且可恢复（重新订阅提醒）；
- 事件：`reminder.sent` / `reminder.skipped`（`reason ∈ {unsubscribed, already_renewed, already_sent}`）。

## 5. 失败与重试

- 至少一次投递 + 退避重试 + 事件幂等（INV-19/25）；
- 达到重试上限 → 转人工，记录最后错误。

## 6. 符合性

- 测试向量：T-61（同窗口重跑幂等）、T-62（退订隔离）；
- 若实现 `+dunning`，按 prior-art.md 的差分模板对照 Stripe smart retries / Recurly dunning 写差分声明。

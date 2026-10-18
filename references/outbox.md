# Outbox 实现机制（唯一权威）

> 定位：MSP 只规定**行为**（INV-18 事务性发箱、INV-19 至少一次 + 幂等消费、INV-25 可重放，
> 见 [msp/events.md](msp/events.md) §3）；本文给 **Go + Postgres 参考实现**与工程坑。
> 概念唯一权威登记在 agent-skills-index 的 `concept-map.md`。

## 1. 三板斧（先记住骨架）

1. 业务事务里**同事务** `INSERT outbox_events` —— 原子性的全部秘密；
2. relay 用 `FOR UPDATE SKIP LOCKED` 抢批次 —— 并发与水平扩容的来源；
3. `published_at` 标记 + 消费端以 `event_id` 幂等 —— 可靠性闭环。

outbox 保证"**不丢**"，幂等键保证"**不重**"，两者必须同时存在（幂等键选型见 msp spec §10）。

## 2. 表设计

```sql
CREATE TABLE outbox_events (
    id            BIGSERIAL PRIMARY KEY,
    event_type    TEXT        NOT NULL,          -- 'order.paid' 等
    aggregate_id  TEXT        NOT NULL,          -- 聚合引用（溯源/分区用）
    payload       JSONB       NOT NULL,          -- 事件负载（保持瘦）
    status        TEXT        NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending','processing','done','dead')),
    retry_count   INT         NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ,                 -- 退避重试调度
    last_error    TEXT,                          -- 仅 dead 时保留原因
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at  TIMESTAMPTZ                    -- 发送/处理完成时刻（DB 时钟，勿用机器时钟）
);
CREATE INDEX idx_outbox_unpublished ON outbox_events (id) WHERE status = 'pending';
```

两个要点：

- 用**状态列**而不是"发完就 DELETE"：发送成功但标记失败会重发；DELETE 会丢掉重试依据。
  已处理记录定期归档到 `outbox_events_archive`，控制主表体积；
- **部分索引**让"捞待处理"的代价只和积压量相关，与表总大小无关。

## 3. 业务侧：同事务写两件事

```go
tx, _ := db.BeginTx(ctx, nil); defer tx.Rollback()
tx.Exec(ctx, `UPDATE orders SET status='paid' WHERE id=$1 AND status='wait_pay'`, id)
tx.Exec(ctx, `INSERT INTO outbox_events (event_type, aggregate_id, payload)
              VALUES ('order.paid', $1, $2)`, id, payload)
tx.Commit()
```

没有事务包裹的 outbox 是**假 outbox**——两步之间崩溃就丢事件或产生不一致。

## 4. Relay：领取与发送（失败隔离）

```go
// 短事务内 claim + 置 processing（锁随事务结束释放）
rows := db.Query(ctx, `SELECT id, event_type, payload FROM outbox_events
                       WHERE status='pending' AND (next_attempt_at IS NULL OR next_attempt_at<=now())
                       ORDER BY id LIMIT $1 FOR UPDATE SKIP LOCKED`, batch)
// 事务外处理；成功 → status='done', published_at=now()；失败 → retry_count+1, next_attempt_at=退避
```

取舍：

- **不在 DB 事务里做网络 IO**（发 MQ/调下游）：锁持有时间拖长，relay 一卡全卡；
  顺序 = claim 并提交 → 处理 → 单独标记；
- 崩溃窗口内可能重复处理 → 这是**至少一次**，由消费端幂等兜底；
- `ORDER BY id` 单 relay 严格有序；多 relay 近似有序。**禁止把全局顺序当保证**（MSP events §3），
  需要 per-aggregate 顺序时按 `aggregate_id` 分片/单分区；
- 一条失败只 `retry_count++` 跳过，不阻塞整批；`retry_count` 超阈值或确定性失败 → `dead` + 告警；
- 领取后进程崩溃的兜底：`processing` 超时（如 5 分钟）由回收任务重置为 `pending`（租约/claim）。

## 5. 死信与人工闭环（对齐课程站 G19）

- `dead` 停止自动领取，保留 `last_error`；
- 后台可列出 `dead`；**重投只允许 dead → pending**（清零 retry、记操作人）；
  **人工完成只允许 dead → done**（payload 记操作人、说明、时间）；非 dead 操作返回 409；
- 这是"最终一致链路最终要有人兜底"的落点，不是装饰。

## 6. 吞吐与延迟

- **batch + drain 连续消费**：批次取满就立刻再取，不等下一个 tick——否则消费速率被 tick 频率锁死
  （真实教训：批 20/3 秒 ≈ 6.7 条/秒，支付 1000 单积压 120 条，见 engineering-pitfalls E-079）；
  参数可配（`OUTBOX_BATCH_SIZE` / `OUTBOX_INTERVAL`），压测校准到与**支付入口速率同量级**；
- `LISTEN/NOTIFY` 只做延迟优化：通知在监听器离线时会丢，轮询永远兜底；
- 多实例高积压空转：调小批次或按 `aggregate_id % N` advisory lock 分片。

## 7. 消费端幂等

```go
res, _ := db.Exec(ctx, `INSERT INTO consumed_events (event_id) VALUES ($1)
                        ON CONFLICT (event_id) DO NOTHING`, e.ID)
if res.RowsAffected() == 0 { return nil /* 重复，直接 ACK */ }
return applyBusinessLogic(ctx, e) // 失败不 ACK，让上游重投
```

outbox 的 `id` 就是消费端幂等键；业务效果幂等仍以业务键为准（msp spec §10）。

## 8. 观测与告警

- 积压量（pending 数）、`retry_count` 分布、`dead` 数进指标与告警；
- 失败事件可查询（含重试次数与 `last_error`）——MSP INV-23/25 的落地。

## 9. 测试方法（对齐 quality-gate-builder 与 E-082）

- 中途杀 relay / 崩溃窗口重放：断言"积压归零 + 权益恰好一份"；
- 乱序与最终一致：验证脚本自带"等到稳定"语义（轮询收敛，别用手速判定红绿）；
- 压测校准吞吐：见 §6。

## 10. 反模式与坑（速查）

1. 假 outbox（业务提交后异步发）；2. 消费者不幂等（重试变重复执行）；
3. 把全局顺序当保证；4. claim 事务里做网络 IO；5. tick 频率锁死吞吐；6. payload 塞大对象；
7. `published_at` 用应用机器时钟；8. 表不归档无限膨胀。

## 11. 什么时候升级

| 信号 | 升级 |
| --- | --- |
| 每秒上千事件 / 跨机房扇出 / 多团队独立消费同一事件流 | 真 MQ：outbox 仍是事实源，relay 转发到 MQ，业务代码不改 |
| 需要延迟任务/定时任务队列 | River（Postgres 任务队列） |
| 所有表变更都要捕获、业务方不肯写 outbox | Debezium CDC（代价：Kafka Connect 运维面，后置） |

默认**自研这套**（核心约 100 行）足以覆盖 90% 场景，不要提前引入 MQ（对齐 lessons-log L-002）。

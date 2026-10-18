# Outbox 实现机制（唯一权威）

> 定位：MSP 只规定**行为**（INV-18 事务性发箱、INV-19 至少一次 + 幂等消费、INV-25 可重放，
> 见 [msp/events.md](msp/events.md) §3）；本文给 **Go + Postgres 参考实现**与工程坑。
> 概念唯一权威登记在 agent-skills-index 的 `concept-map.md`。

## 1. 三板斧（先记住骨架）

1. 业务事务里**同事务** `INSERT outbox_events` —— 原子性的全部秘密；
2. relay 用 `FOR UPDATE SKIP LOCKED` 抢批次 —— 并发与水平扩容的来源；
3. `published_at` 标记 + 消费端以 `event_id` 幂等 —— 可靠性闭环。

outbox 保证"**不丢**"，幂等键保证"**不重**"，两者必须同时存在（幂等键选型见 msp spec §10）。

## 2. 同库独立表是硬约束（不是方便起见）

- **同库 = 事务边界**：本地 ACID 事务只覆盖同一个数据库。把 outbox 放到 Redis/Kafka 里，
  那两步就变跨系统调用，"同时成功/同时失败"重新变成无解问题——模式直接失效；
- **独立表，而不是业务表加布尔字段**：一个变迁可能要发多个事件（支付成功要发"已支付+通知+积分"）；
  多个消费者进度各自独立（一个布尔位表达不了"谁收过谁没收过"）；
  relay 高频扫"未发送"要与订单正常读写隔离；事件 schema / 重试 / 归档与业务字段演进节奏不同；
- **每服务（每限界上下文）一张自己的 outbox**，不跨库共用；分库分表场景下每个分片各一张、各配一个 relay；
- relay 位置自由：与业务服务**同进程起一个 goroutine** 最常见，零额外部署成本；
- **唯一例外（CDC）**：Debezium 监听 WAL 可以省掉应用写表（"隐式 outbox"）。更稳的混合做法是
  **仍建一张专用 outbox 表**，应用只往这张表写事件、Debezium 监听它——既保留同事务可靠性，
  又把"哪些变化值得成为事件"的决策收拢一处，不把内部表结构细节广播给所有消费者。

## 3. 表设计

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
- 补充：`id` 既是排序键也是消费端幂等键；`aggregate_id` 用于 per-aggregate 顺序与分片；
  payload 内带 schema `version`（字段只加不改，对齐 CloudEvents version）；
  归档优先**按月分区 + 到期 drop**（热表 vacuum 压力会造成全库事故，见 engineering-pitfalls 磁盘教训）。

## 4. 业务侧：同事务写两件事

```go
tx, _ := db.BeginTx(ctx, nil); defer tx.Rollback()
tx.Exec(ctx, `UPDATE orders SET status='paid' WHERE id=$1 AND status='wait_pay'`, id)
tx.Exec(ctx, `INSERT INTO outbox_events (event_type, aggregate_id, payload)
              VALUES ('order.paid', $1, $2)`, id, payload)
tx.Commit()
```

没有事务包裹的 outbox 是**假 outbox**——两步之间崩溃就丢事件或产生不一致。

## 5. Relay：领取与发送（失败隔离）

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
- 停机语义：收到 SIGTERM 先 **drain 完当前批**再退出，避免把半批丢回重试。

## 6. 死信与人工闭环（对齐课程站 G19）

- `dead` 停止自动领取，保留 `last_error`；
- 后台可列出 `dead`；**重投只允许 dead → pending**（清零 retry、记操作人）；
  **人工完成只允许 dead → done**（payload 记操作人、说明、时间）；非 dead 操作返回 409；
- 这是"最终一致链路最终要有人兜底"的落点，不是装饰。

## 7. 吞吐与延迟

- **batch + drain 连续消费**：批次取满就立刻再取，不等下一个 tick——否则消费速率被 tick 频率锁死
  （真实教训：批 20/3 秒 ≈ 6.7 条/秒，支付 1000 单积压 120 条，见 engineering-pitfalls E-079）；
  参数可配（`OUTBOX_BATCH_SIZE` / `OUTBOX_INTERVAL`），压测校准到与**支付入口速率同量级**；
- `LISTEN/NOTIFY` 只做延迟优化：通知在监听器离线时会丢，轮询永远兜底；
- 多实例高积压空转：调小批次或按 `aggregate_id % N` advisory lock 分片。

## 8. 消费端幂等

```go
res, _ := db.Exec(ctx, `INSERT INTO consumed_events (event_id) VALUES ($1)
                        ON CONFLICT (event_id) DO NOTHING`, e.ID)
if res.RowsAffected() == 0 { return nil /* 重复，直接 ACK */ }
return applyBusinessLogic(ctx, e) // 失败不 ACK，让上游重投
```

outbox 的 `id` 就是消费端幂等键；业务效果幂等仍以业务键为准（msp spec §10）。
`consumed_events`（inbox）同样必须落在**消费方自己的数据库**里——"同库"约束对两侧对称。

## 9. 观测与告警

- 积压量（pending 数）、`retry_count` 分布、`dead` 数进指标与告警；
- **最老 pending 的 age** 也要告警——积压清零但最老一条永远卡着，是比数量更准的"卡死"信号；
- 失败事件可查询（含重试次数与 `last_error`）——MSP INV-23/25 的落地。

## 10. 测试方法（对齐 quality-gate-builder 与 E-082）

- 中途杀 relay / 崩溃窗口重放：断言"积压归零 + 权益恰好一份"；
- 乱序与最终一致：验证脚本自带"等到稳定"语义（轮询收敛，别用手速判定红绿）；
- 故障注入先修工具自身（E-083：只在失败时走的那几行最没被测过）；
- 压测校准吞吐：见 §7。

## 11. 反模式与坑（速查）

1. 假 outbox（业务提交后异步发）；2. 消费者不幂等（重试变重复执行）；
3. 把全局顺序当保证；4. claim 事务里做网络 IO；5. tick 频率锁死吞吐；6. payload 塞大对象；
7. `published_at` 用应用机器时钟；8. 表不归档无限膨胀；9. outbox 表与业务表不在同一库（跨系统，模式失效）；
10. 多个服务共用一张 outbox 表（跨事务边界）。

## 12. 什么时候升级

| 信号 | 升级 |
| --- | --- |
| 每秒上千事件 / 跨机房扇出 / 多团队独立消费同一事件流 | 真 MQ：outbox 仍是事实源，relay 转发到 MQ，业务代码不改 |
| 需要延迟任务/定时任务队列 | River（Postgres 任务队列） |
| 所有表变更都要捕获、业务方不肯写 outbox | Debezium CDC（代价：Kafka Connect 运维面，后置） |

默认**自研这套**（核心约 100 行）足以覆盖 90% 场景，不要提前引入 MQ（对齐 lessons-log L-002）。

## 13. 拓扑与角色：生产者 → relay → MQ → 消费者

```
业务服务               relay                 MQ              下游服务
(事实生产者)          (投递员/搬运工)        (邮局)          (消费者)
  ├─ 写业务表+outbox
  │  （同一事务）
  │                  ├─ 读 outbox（SKIP LOCKED）
  │                  ├─ publish ────────→ ├─ 投递 ────────→ ├─ 消费（inbox 幂等）
```

四角色的**失败域各管一段**，这也是拓扑的价值：

注意 **relay 的双重身份**：对 outbox 表它是消费者（把 pending 行读走），对 MQ 它是生产者
（下游订阅 topic 的服务才是消费者）——它是把事件从"数据库世界"搬进"消息世界"的搬运工，
不属于任何一方的业务逻辑，这正是它独立存在的意义。

| 角色 | 挂了会怎样 | 恢复后 |
| --- | --- | --- |
| 业务服务 | 无新事实产生 | 无需动作（事实没写 = 事件没写，同事务） |
| relay | outbox 只积压、不丢 | SKIP LOCKED 继续捞，积压自然消化 |
| MQ | publish 失败进入 retry_count 退避 | 重试成功 |
| 消费者 | MQ 保留/重投；直连模式下 outbox 不确认 | 幂等消费（inbox）继续 |

**两种投递形态**：

- **直连（模块化单体默认）**：relay 直接调用进程内/同库的下游处理器——四角色塌缩成两个
  （生产者 + 分发器），不需要"邮局"；课程站的 `workers.go` 就是这个形态；
- **经 MQ（跨进程）**：出现 §12 的升级信号（每秒上千 / 跨机房 / 多团队独立消费）才引入；
  outbox 仍是事实源，relay 只是搬运工。

工程要点：

- **信封端到端不变**：无论走直连还是 MQ，消费者看到的是同一 CloudEvents 信封，
  不该感知"上一跳是 relay 还是 MQ"；
- **per-aggregate 顺序**：经 MQ 时用 `aggregate_id` 做分区键（Kafka key），单分区内保序；
- **开源对照**：该模式源自 Chris Richardson《microservices.io》的 Transactional Outbox；
  .NET 生态的 MassTransit / NServiceBus 把 outbox + inbox 做成了一体默认（值得作为先例对表）；
  Go 的 Watermill 自带 SQL outbox publisher（见 §12）。

### 13.1 outbox 与 MQ：接力，不是替代

| | outbox | MQ |
| --- | --- | --- |
| 解决什么 | **不丢**（写侧：先落库，崩溃不丢） | **怎么送**（读侧：缓冲 / 扇出 / 解耦） |
| 本质 | 写库的 durability 缓冲 | 消息分发系统 |
| 位置 | 生产者库内 | 生产者与消费者之间 |

直连下游（无 MQ）可行，但会失去四样：**缓冲削峰**（下游挂/慢时 relay 阻塞，事件积压在 outbox，
而 outbox 表按"少量待投递"设计，高积压下查询变慢）、**扇出**（一个事件喂 N 个下游要逐个调、
逐个记重试，新增下游就要改 relay）、**消费进度**（MQ 天然给每个消费者独立的 offset / 重试 / 死信，
点对点要自造）、**跨团队解耦**（对方发布节奏会拖住你）。

中间玩法：**消费者直接扫 outbox 表**（各自 `consumed_events` 记进度 + `LISTEN/NOTIFY` 唤醒），
让 Postgres 兼职消息队列（River 的思想）。适合**同库内的异步任务**，不适合系统级事件分发——
N 个消费者会把生产库读压力放大 N 倍，跨库还要开网络权限。

一句话分流：**"事件丢了行不行" → 不行，就要 outbox；"下游有几个、会不会挂、流量会不会抖"
→ 多 / 会 / 抖，就要 MQ。** outbox 保生存，MQ 保优雅。

# 参考架构与设计不变量

## 1. 总体形态

单个业务系统 = **一个后端服务（模块化单体）+ 一个前端应用 + 一个 PostgreSQL**。

- 模块按 `domain（实体与规则）/ app（用例）/ infra（SQL 存储）/ http（接口）` 分层；
- 模块之间只通过两类方式交互：domain 接口调用、`outbox_events` 事件；
- 不为"将来可能拆微服务"提前引入微服务；模块边界清晰即足够，未来拆分是机械动作。

## 2. 领域模块清单（按需裁剪）

| 模块 | 职责 | 关键不变量 |
| --- | --- | --- |
| identity | 注册/登录/JWT | 密码 bcrypt；token 短周期 + 可撤销（session 表） |
| catalog | 商品/报价（Product/Offer） | 前端只提交 `offer_id`；价格与售卖规则由服务端决定 |
| commerce | 订单状态机 | 状态只允许单向流转；金额、条目全部快照 |
| payment | 支付单、金额指纹、到账匹配、退款工单 | 一个收款账户一个匹配域；所有入账幂等 |
| entitlement | 权益（谁能访问什么） | **唯一判权入口**；`(user_id, product_id) active` 唯一 |
| membership | 订阅周期 | 周期顺延不丢天数 |
| points | 积分账本 | 余额变动 = 流水 + 余额快照，同事务 |
| gifts | 礼物库存与赠送 | 库存扣减与流水同事务；收藏型限量防超卖 |
| shipping | 收货地址与发货 | 订单地址快照；发货幂等 |
| admin | 运营后台 | 基于 `admin_users` 的角色校验；退款审核即冲销 |
| notify | 站内通知与提醒 | 提醒去重表保证幂等（多实例安全） |
| analytics | 行为事件 | 只追加；不阻塞主链路 |

## 3. 核心链路（所有品类共用一条成交路径）

```
下单 → 订单(pending) → 支付（收款码/网关）→ 支付成功事件(outbox)
     → fulfillment 按商品类型分派 → 发权益 / 入积分 / 入礼物 / 生成发货单
     → 订单 fulfilled
```

关键点：

- **新增品类不新增成交路径**。课程、会员、电子书、礼物、积分包、周边都是 `products` 的一种 `type`，用 `offers.kind` 描述一次性/永久/订阅。
- **履约按商品类型分派**：内核提供分派器，商品类型的处理器注册到类型注册表（最小实现可用
  `switch` 起步，升级为注册表以支持插件，见 [plugin-architecture.md](plugin-architecture.md)）。
- **积分兑换也是订单**（`payment_mode=points`），走同一套 outbox 履约，不开旁路。

## 4. 事务性发箱（outbox）

```
业务事务：更新订单/支付单 + 插入 outbox_events（同一事务）
worker  ：FOR UPDATE SKIP LOCKED 领取 → 执行处理器 → done / 失败退避重试
```

约定：

- 处理器必须**幂等**（重试会重放整个事件）；
- 幂等键：事件驱动入账一律用复合唯一——积分 `(event_id, ref_id)`、礼物 `(event_id, product_id)`；
  单列 `event_id` 唯一不满足 MSP（INV-15）；
- 事件即数据：可查询、可统计、可按 id 手动重放；
- 需要跨进程/跨机房时再加 relay 转发到消息队列，outbox 表仍是事实来源。

**不引入消息队列中间件**，除非满足以下任一条件：事件量到每秒上千、需要跨机房扇出、多团队独立消费同一事件流。

## 5. 状态机

订单：

```
pending → paid → fulfilled
pending → cancelled | closed（超时）
paid|fulfilled → refunding → refunded
```

退款工单（MSP v0.2.0）：

```
applied → processing → succeeded | failed
applied → succeeded        （无外部资金通道的即时冲销，如人工转账后登记）
applied → rejected | cancelled
processing → cancelled
```

支付单：`created → pending → succeeded | failed | expired`，退款后 `refunded`。

规则：

- 状态更新一律**条件更新**（`UPDATE ... WHERE status = '预期状态'`），用影响行数判断是否重复执行；
- 支付窗口（默认 15 分钟）到期后关单，并释放未支付的金额占用与支付单。

## 6. 判权与展示

- 内容/资源上保存"访问级别"（`public` / `members` / `product`），判权时全部走 entitlement 查询；
- 无权访问时**保留元信息、清空正文、标记 locked**（列表页体验），详情页展示解锁引导；
- 会员权益到期 → worker 置 expired；7/3/1 天前发续费提醒（去重表保证只发一次）。

## 7. 金额与时间

- 金额一律 `bigint`，单位「分」；展示时再格式化；禁止浮点参与金额运算；
- 时间存 `timestamptz`（UTC），展示层转换；不要存本地时间字符串；
- 所有写入带 `created_at`，可变实体带 `updated_at`（触发器维护）。

## 8. 安全底线

- 密码 bcrypt；JWT 用 HS256/RS256，密钥只从环境变量读；
- 内部回调（监听端、网关）必须验签 + 防重放（nonce 唯一 + 时间窗）；
- 管理接口必须经过 `admin_users` 角色校验；
- 密钥/凭据永不进仓库、镜像、日志；构建凭据放服务器配置文件或 CI Secret。

## 9. 内核与插件边界

- 内核 = 完备闭环（§3 链路）+ 稳定扩展面；业务"花样"一律走扩展点注入，不修改内核；
- 扩展点目录、插件 manifest/生命周期、隔离与失败边界、符合性门禁见 [plugin-architecture.md](plugin-architecture.md)；
- 依赖单向：插件 → 内核；内核不 import 插件；插件之间通过事件协作；
- 任何插件合并前必须通过全部既有 MUST 向量（回归门禁）。

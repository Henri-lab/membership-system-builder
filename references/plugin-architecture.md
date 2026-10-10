# 内核与插件架构（完备闭环 + 插件注入）

> 目标：本技能生成的项目是一个**完备闭环的基础设施**——身份 / 目录 / 订单 / 支付 / 履约 / 权益 /
> 积分 / 礼物 / 退款 / 对账 / 审计全部打通；业务"花样"（打赏、分销、答题、直播、排行榜等）
> 一律通过扩展点注入，**不修改内核**。
> 借鉴的公开设计：Kill Bill（核心引擎 + 插件 API、OSGi 隔离）、Medusa（模块/插件/订阅者/工作流）、
> Spree（促销规则/动作/计算器）、Sylius（声明式状态机）、hexagonal（端口-适配器）。

## 1. 内核 vs 插件（边界）

**内核**（不可随意修改）：9 个领域模块 + outbox + 状态机 + MSP 不变量。内核只承诺两件事——
① 完备闭环：任何一单从下单到退款都能走完；② 稳定扩展面：只通过 §2 的扩展点向外开放。

**插件**（可任意加）：新商品类型、新支付渠道、新业务事件处理、促销、通知渠道、页面挂载、定时任务。
插件可自带数据表/迁移/配置/UI，但**只加不改**：禁止改变内核既有语义（extensions.md 加法原则的强化）。

**依赖方向：插件 → 内核，单向**。内核不 import 任何插件（对应 Kill Bill 的 `killbill-api`
单向依赖、Medusa 的 Module 边界）。

## 2. 扩展点目录（SPI）

| # | 扩展点 | 注入方式 | 借鉴 | 例子 | 禁止 |
| --- | --- | --- | --- | --- | --- |
| 1 | 商品类型 `Product.type` | 履约处理器注册表 `Fulfill(type)` | Kill Bill 插件 API 思想 | `course_bundle` → 发权益+积分 | 内核写 `switch` 或插件专属 `if` |
| 2 | 售卖方式 `Offer.kind` | 周期推导 + proration 策略（枚举 `none/create_prorations/always_invoice`） | Stripe proration | `enterprise` → 合同周期 | 改变既有 kind 语义 |
| 3 | 支付渠道 `Payment.provider` | `PaymentProvider` 接口（create/query/refund） | Kill Bill `PaymentPluginApi` | `wechat_native` | 绕过 OP-P2 验真与幂等 |
| 4 | 退款资金通道 | `RefundExecutor`（打款 / 仅登记） | Kill Bill 支付插件 | 网关自动退 / 个人码人工转账登记 | 只打款不回退权益（违反 INV-16） |
| 5 | 定价与优惠 | `PricingCalculator` 链（依次计算运费/折扣） | Spree calculators | 会员折扣、满减 | 改订单快照（INV-2） |
| 6 | 促销 | `PromotionRule` + `PromotionAction` | Spree promotion engine | 满 N 送礼物 | 直接改余额/库存（必须走 OP-N / Gift 语义） |
| 7 | 流水类型 `kind` | 枚举扩展（`x-` 前缀） | Lago wallet transactions | `x-campaign` 活动奖励 | 另开余额旁路（必须走账本） |
| 8 | 事件订阅 | outbox 事件订阅者（幂等、可重放） | Medusa subscribers | `order.paid` → 打榜/通知/埋点 | 阻塞主链路、依赖全局顺序 |
| 9 | 通知渠道 | `Notifier` 接口（inapp/email/sms/webhook） | Medusa 通知模块 | 邮件提醒 | 忽略退订/去重 |
| 10 | 权益范围 `Entitlement.scope` | 枚举扩展 | Kill Bill entitlement | 章节级授权 | 绕过 INV-3 判权 |
| 11 | 状态机扩展 | 声明式状态机（状态/迁移为数据，只允许加法迁移） | Sylius Winzou state machine | 新增 `paused` 状态 | 复用既有状态名改义 |
| 12 | 前端挂载点 | 管理端 section/菜单 + 用户端插槽 | Medusa Admin extensions | 礼物管理页 | 改核心 API 契约 |
| 13 | 定时任务 | scheduler 注册（幂等、多实例安全） | Medusa scheduled jobs | 超时关单、榜单归档 | 与既有 worker 去重缺失 |
| 14 | 埋点 | analytics 事件（`x-` 命名空间、匿名可用） | Medusa analytics module | 页面浏览/停留 | 采集敏感字段 |

## 3. 插件契约（manifest + 生命周期）

manifest 最小字段：`name`、`version`、`compat`（内核/协议版本范围，semver 区间）、
`capabilities`（注册的扩展点）、`events`（订阅的事件）、`routes`（HTTP/页面挂载）、
`migrations`（自有表版本化迁移）、`config_schema`。

生命周期：`load(config) → register() → start() → health() → stop()`；
配置按租户/环境隔离（借鉴 Kill Bill 的 per-tenant plugin config）。

## 4. 隔离与失败边界

- 默认**进程内接口注入**（Go interface + registry；Node 同理）。需要硬隔离（多语言/不可信代码）
  时再上独立进程（hashicorp go-plugin）或 OSGi（Kill Bill）——小团队不必；
- 插件异常不得破坏核心事务：核心调用插件走明确错误契约；事件订阅者失败只重试该订阅者的事件、
  写 `last_error`，**禁止**让订单主链路失败；
- 数据所有权：插件自有表 + 版本化迁移；禁止跨模块直连他人表（只能经 domain 接口或事件）；
- 禁止反向依赖：内核不 import 插件，插件不 import 其他插件（确需协作走事件）。

## 5. 符合性门禁

- 任何插件合并前必须通过内核全部既有 MUST 向量（回归不变，extensions.md）；
- 插件必须声明它依赖/增强的 MSP 等级，并附差分用例（prior-art.md §3）；
- 两个插件注册同一扩展点的冲突必须有显式决策规则（声明顺序/优先级），禁止静默覆盖。

## 6. 示例：用插件实现"打赏礼物 + 榜单"，内核零改动

1. 商品类型 `gift`（内核若没有）→ 注册 `Fulfill` 处理器：入库 + 限量校验；
2. 订阅 `order.paid` → 榜单订阅者：累计总榜/月榜（自有表）；
3. 挂载管理端 section：礼物与榜单页面；
4. `Notifier` 插件：收到礼物发站内信。

内核未改一行；全部通过注册与订阅完成。

## 7. 反模式

- 在核心 fulfillment 写 `switch` 或插件专属 `if`（应使用注册表）；
- 插件直接 UPDATE 他人表、绕过账本或绕过 INV-3 判权；
- 订阅者阻塞主链路或依赖事件顺序；
- 扩展点冲突被静默覆盖；
- 把"项目特有规则"写死进内核——确需通用化的规则走 lessons-log → architecture/pitfalls 的提升流程。

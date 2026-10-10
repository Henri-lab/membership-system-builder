# MSP：会员订阅支付协议标准（Membership & Subscription Protocol）

> 版本：v0.3.0（2026-10-10）｜性质：**规范性协议**（normative），不是某个语言的实现模板。
> 作者：henrifox｜上游：<https://github.com/Henri-lab/membership-system-builder>｜许可：MIT（见仓库 LICENSE）
> 引用本协议请注明：MSP v0.3.0 + 作者 + 上游仓库地址（引用格式见仓库 README「起源与署名」）。

## 这是什么

把"订单 / 会员 / 积分 / 支付 / 权益"系统的**行为契约**独立于语言、框架与中间件抽出来，
定义成一组成员可验证的规则：

```
对象模型（有哪些实体） + 操作（接口 + 输入输出 + 副作用）
        + 全局不变量（MUST 规则） + 事件契约 + 符合性判定（怎么算可用）
```

只要一个实现满足声明范围内的全部 MUST 规则，就判定它是**符合 MSP 的可用系统**——
不论它用 Go/Java/Node 写、用 Postgres/MySQL 存、用 outbox/MQ 传递事件。

## 文件

| 文件 | 内容 | 何时读 |
| --- | --- | --- |
| [spec.md](spec.md) | 对象模型、状态机、**操作定义（输入/输出/副作用/错误）**、全局不变量 | 实现前必读 |
| [events.md](events.md) | 事件信封、必需事件与 payload、投递与消费语义 | 设计事件/履约时 |
| [ledger.md](ledger.md) | **积分账本规范**（唯一事实来源 / 只追加 / 结构化幂等键 / 原子扣减 / 对账） | 实现或评审积分时必读 |
| [conformance.md](conformance.md) | 符合性等级、MUST 清单、**设计判据清单（D-1~D-5）**、测试向量、判定规则与证据格式 | 验收时必读 |
| [extensions.md](extensions.md) | 扩展机制（新商品类型/渠道/积分类型/多租户）与兼容规则 | 需要超出基线能力时 |
| [prior-art.md](prior-art.md) | 成熟先例映射（Stripe / Lago / Kill Bill / CloudEvents / IETF 幂等草案）与差分声明要求 | 设计决策、移植参考实现、评审时 |

## 用法（三步）

1. **声明范围**：从符合性等级里选（Core / Subscriptions / Points / Gifts / Physical /
   Disputes / Invoicing / MultiCurrency），可以只实现子集；
2. **实现**：按 spec.md 的对象与操作落地；语言与存储自由选择；
3. **验收**：跑 conformance.md 的测试向量，产出符合性报告；MUST 全过 = 系统可用，SHOULD 未过 = 记录为已知偏差。

## 设计立场

- **面向行为，不面向实现**：协议只规定"外部可观察的行为与状态不变量"，不规定表名、字段名、进程拓扑。
- **单一事实来源**：权益、积分、订单各自只有一处权威状态；协议明确禁止"从订单推断权益"这类旁路。
- **一切资金变动可重放**：幂等键与事件语义是一等公民，不是实现细节。
- **扩展靠加法**：新增能力只能新增类型/事件/字段，不能改变既有语义。
- **对齐成熟先例**：对象/状态/事件语义尽量对齐 Stripe、Lago、Kill Bill、CloudEvents 与 IETF 幂等草案；
  只在无先例处自创（如个人收款码的金额指纹），差异必须在 [prior-art.md](prior-art.md) 中声明。

## 后续候选（v0.4+，欢迎按 [extensions.md](extensions.md) 的加法原则补充）

| 主题 | 现状 | 补充方向 |
| --- | --- | --- |
| 续费提醒与通知契约 | 仅事件层面提及 | 定义提醒时机、渠道降级、用户退出（退订）语义 |
| 埋点与画像 | 未覆盖 | 定义事件采集最小集与隐私边界 |
| 账户合并 / 迁移 | 未覆盖 | 定义主体合并时的权益/积分迁移规则 |

> v0.3 已把"部分退款、试用与 proration、拒付/争议、税务发票、多币种"纳入正文
> （[spec.md](spec.md) §8 + [conformance.md](conformance.md) T-39~T-50）。

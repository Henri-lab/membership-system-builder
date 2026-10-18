---
name: membership-system-builder
description: 为「会员订阅 + 付费内容 + 支付」业务完成选型并生成可直接执行的构建技能，供任何代码能力达标的 agent 从零搭出可理解、可维护、可演进的系统；也用于对既有会员/支付系统做 MSP 协议符合性审计、支付链路设计评审与协议答疑。覆盖个人收款码（金额指纹 / 截图凭证审核 / 聚合服务商）与官方网关、订阅、积分、礼物、退款、拒付、发票、多币种与插件扩展；不适用于只对接现成计费平台（Stripe/Paddle/RevenueCat）的小改动。
---

# 会员订阅支付系统构建器

## 产出物

一次运行产出**两份东西**：

1. 一份**选型结论**（写进产出技能的「分支决策」章节，不超过一页）。
2. 一份**针对该项目的构建技能目录**（`SKILL.md` + `references/`），任何 agent 读它就能从零实现系统、按里程碑验收。

不产出业务代码本身——本技能负责把"怎么建、按什么顺序建、每一步怎么验收"讲清楚。

## 第一步：确认选型分支

执行时先按 [references/solution-tiers.md](references/solution-tiers.md) 做一次**必做的选型访谈**，
一次问清三件事——**目的**（验证想法 / 自用经营 / 商业产品 / 多产品基础设施）、**规模**
（日订单量级、团队、预算）、**硬约束**（执照与备案、技术栈、地区合规）——然后从档位矩阵选档，
把「目的 × 规模 → 档位 → 分支取值 → 理由（含为什么不是上一档/下一档）」写进产出的分支决策章节。
**禁止静默默认**：用户未回答的项按最保守假设处理，并在产出中显式标注"未确认"。

| 档位 | 目的 × 规模 | 典型方案 |
| --- | --- | --- |
| L0 最小验证 | 验证想法，<10 单/日，零预算 | `personal_qr` + 截图审核/金额指纹 + `single_host_compose` |
| L1 独立经营 | 自用小站，<100 单/日，solo | `personal_qr` + `hybrid` 或 `aggregation_webhook` |
| L2 商业产品 | 商业运营，<1000 单/日，有执照+备案 | `official_gateway` + `+dunning` + `tax_snapshot` |
| L3 可复用基础设施 | 多产品复用 | L2 全量 + 插件内核 + 独立身份层 |

> 档位判据、理由模板与换档触发器见 solution-tiers.md；下表是**分支取值全集**，落档后逐项确认。

| 分支 | 取值 | 默认 |
| --- | --- | --- |
| 收款方式 | `personal_qr` / `official_gateway` / `hosted_billing` | `personal_qr` |
| 到账确认（personal_qr） | `amount_fingerprint` / `screenshot_review` / `hybrid` / `aggregation_webhook` | `screenshot_review` |
| 地区合规 | `cn_mainland` / `overseas` | `cn_mainland` |
| 技术栈 | `go_next_pg` / `node_next_pg` / `existing_stack` | `go_next_pg` |
| 部署形态 | `single_host_compose` / `multi_node` / `serverless` | `single_host_compose` |
| 账号体系 | `standalone` / `reuse_existing` | `standalone` |
| 业务范围 | `membership_content` / `+points` / `+gifts` / `+merch` / `+consulting`（可多选） | `membership_content` |
| 规模 | `solo` / `small_team` | `solo` |
| 退款深度 | `whole_order` / `+partial`（部分退款与段回收） | `whole_order` |
| 拒付争议 | `none` / `manual_dispute`（人工登记） | `none` |
| 试用与按比例 | `none` / `trial` / `+proration` | `none` |
| 续费催收 | `inapp_reminder` / `+dunning`（多档催收） | `inapp_reminder` |
| 税务发票 | `none` / `tax_snapshot` | `none` |
| 多币种 | `single_currency` / `+fx_snapshot` | `single_currency` |
| 账户合并 | `none` / `+merge`（后置） | `none` |
| 插件形态 | `inprocess_registry` / `separate_process` | `inprocess_registry` |

`reuse_existing`（改造已有项目）时：先读现有代码与数据库，产出**改造计划**而不是重写计划；把哪些表/模块复用、哪些新增讲清楚。
`standalone` 的注册/登录/会话/密码重置按 **identity-system-builder（ASP 协议）** 实现；本技能只消费其签发的 `principal`。
新增分支默认取最小实现；选中的分支必须产出与成熟参考（`prior-art.md`）的**差分声明**。

## 第二步：按分支读取参考

**始终读取：**

- [references/solution-tiers.md](references/solution-tiers.md) —— **选型访谈与方案档位矩阵**（第一步必读：问什么 / 怎么选档 / 怎么讲理由）

- [references/msp/README.md](references/msp/README.md) —— **MSP 协议标准**（对象/操作/副作用/不变量/事件/符合性判定的总览，先读它决定深入哪一篇）
- [references/msp/spec.md](references/msp/spec.md) —— 协议正文（对象模型、状态机、操作定义、30 条全局不变量）
- [references/msp/ledger.md](references/msp/ledger.md) —— **积分账本规范**（唯一事实来源 / 只追加 / 结构化幂等键 / 原子扣减 / 对账）
- [references/msp/conformance.md](references/msp/conformance.md) —— 符合性等级、MUST 清单、54 条测试向量与判定规则
- [references/msp/events.md](references/msp/events.md) —— 事件信封与必需事件契约
- [references/outbox.md](references/outbox.md) —— **Outbox 实现机制**（Go+Postgres 参考实现 / 领取与退避 / 死信闭环 / 吞吐与观测）
- [references/msp/extensions.md](references/msp/extensions.md) —— 扩展机制与兼容规则
- [references/msp/prior-art.md](references/msp/prior-art.md) —— **成熟先例映射**（Stripe / Lago / Kill Bill / CloudEvents / IETF 幂等草案）与差分声明要求
- [references/data-retention.md](references/data-retention.md) —— **数据保留与删除**（三类数据 / 保留期 / 删除权与只追加账本的共存规则）
- [references/plugin-architecture.md](references/plugin-architecture.md) —— **内核与插件架构**（完备闭环 + 扩展点目录 + 插件契约；借鉴 Kill Bill / Medusa / Spree / Sylius）
- [references/architecture.md](references/architecture.md) —— 参考架构、领域划分、不可妥协的设计不变量
- [references/data-model.md](references/data-model.md) —— 表目录与关键约束（按业务范围裁剪）
- [references/delivery-plan.md](references/delivery-plan.md) —— 阶段划分与验收标准
- [references/pitfalls.md](references/pitfalls.md) —— 真实踩坑清单（生成时按分支挑选相关条目）
- [references/lessons-log.md](references/lessons-log.md) —— **经验账本**：使用本技能前先扫最近条目；本轮结束后把新经验按格式追加进去
- [references/maintenance.md](references/maintenance.md) —— **技能维护手册**：何时追加、如何去重、何时把条目提升进正文、如何新增分支

> 学习/教学资料（生成时不必读）：[references/design-walkthrough.md](references/design-walkthrough.md) ——
> 用正常与边界例子讲清"为什么这样设计"（含支付窗口宽容期与真实 hook 迁移说明）。
> [references/design-judgment.md](references/design-judgment.md) —— **加字段还是加对象？**
> 六问判定法 + 三个杀手测试 + 正反例子（新增功能前先过一遍）。
> [references/master-craft.md](references/master-craft.md) —— **老师傅的隐形知识**：十篇权威判据
> （Helland 四个 I / Kleppmann 派生数据 / Fowler 段 / Evans 聚合 / Stripe / AWS）的出处、原话与 MSP 落点，
> 加上五个代码评审测试（删表重建 / 审计 / 并发同发 / 重放 / 回滚）与"新手直觉 vs 老师傅"对照表。

**按收款方式读取：**

- `personal_qr` → [references/payment-confirmation.md](references/payment-confirmation.md)（先读，选确认策略）→
  [references/payment-personal-qr.md](references/payment-personal-qr.md)（金额指纹实现细节）
- `official_gateway` / `hosted_billing` → [references/payment-official.md](references/payment-official.md)

**按业务分支读取：**

- `inapp_reminder` / `+dunning` → [references/reminder-contract.md](references/reminder-contract.md)
- `+merge` → [references/account-merge.md](references/account-merge.md)（后置）

只读与当前分支相关的参考，不要把全部内容塞进产出技能。

## 第三步：生成构建技能

用 [assets/generated-skill-template/SKILL.md.tmpl](assets/generated-skill-template/SKILL.md.tmpl) 作为骨架，写出目标项目的技能目录（模板以 `.tmpl` 结尾是刻意的：避免被技能扫描器误注册为一个技能）：

```text
<目标目录>/<project-name>-builder/
├── SKILL.md              # 目标、分支决策、里程碑、验收标准
└── references/
    ├── data-model.md     # 本项目裁剪后的表结构（含关键索引与约束）
    ├── payment.md        # 本项目选定的支付链路（含对账与兜底）
    ├── extensions.md     # 本项目开放的扩展点清单与插件契约（按业务范围裁剪）
    ├── delivery.md       # 阶段任务清单 + 每阶段验收命令
    └── ops.md            # 部署、备份、密钥轮换、故障排查
```

输出目录：用户指定则用指定目录；否则放当前工作区 `skills/<project-name>-builder/`，并说明安装到 `${CODEX_HOME:-$HOME/.codex}/skills/` 后即可被 agent 发现。

生成内容**必须包含**（缺一项即视为未完成）：

1. **目标与非目标**：明确系统边界（例如"不做自动退款、不做物流 API"）。
2. **分支决策表**：访谈结论（目的/规模/硬约束）、所选档位与理由（含为什么不是相邻档位）、未确认假设，一两句话一项。
3. **领域模型与数据表**：按业务范围裁剪后的表、关键字段、唯一索引与状态机。
4. **支付链路**：到账确认策略（指纹自动 / 截图凭证审核 / 聚合回调）+ 金额指纹或网关回调完整流程
   （创建 → 到账 → 匹配/验签 → 履约），以及退款与兜底（漏单举证）。
5. **里程碑 + 验收标准**：每阶段必须有"可执行的真实验收"（真实数据库端到端冒烟），而不是"编译通过"；
   验收标准必须对齐 **MSP 符合性等级**（Core / Subscriptions / Points / Gifts / Physical），
   并逐条通过 `references/msp/conformance.md` 的**设计判据清单（§3 D-1~D-5）**与测试向量；
   可从 [assets/conformance-smoke.sh.tmpl](assets/conformance-smoke.sh.tmpl) 复制可执行验收骨架（按本项目端点/鉴权调整）；
   对每个与成熟参考不同的语义，给出差分用例（`references/msp/prior-art.md` §3）。
6. **踩坑清单**：从 `pitfalls.md` 挑选与本分支相关的条目（至少覆盖支付与幂等两类）。
7. **运维手册**：部署方式、备份、对账命令、密钥轮换、常见故障定位。
8. **扩展点清单**：内核闭环（完备成交/退款链路）+ 本项目开放哪些扩展点、插件 manifest 与符合性门禁
   （裁剪自 `references/plugin-architecture.md`）；"花样"一律注入，不修改内核。

## 不可妥协项（任何产出都必须写入）

1. **权益（entitlement）是唯一判权事实来源**；续费在 `max(原到期时间, now())` 上顺延。
2. **支付匹配域全局唯一**：一个收款账户只能有一个消费者；多系统共用账户时必须分区金额空间。
3. **资金与事件同事务**（outbox 或等价机制）；所有入账幂等、可重放。
4. **退款必须回收权益/积分/礼物**；回收不满足时宁可转人工，也不能"退了钱东西还在"；
   部分退款按行回收且 Σ 成功退款 ≤ 已付（INV-28）。
5. **账本是唯一事实来源**：金额用整数"分"；余额 = Σ delta 且可重建；账本只追加不可变；扣减必须原子（条件更新/行锁）；
   事件驱动入账必须用 `(source_event_id, ref)` 复合幂等键（详见 [references/msp/ledger.md](references/msp/ledger.md)）。
6. **凭据永不进仓库、镜像、日志**；构建凭据单独放服务器/CI 配置。
7. **每个阶段以真实数据库端到端冒烟验收**；把验证输出写进文档。
8. **声明 MSP 符合性等级**：生成的系统必须显式声明实现了哪些等级，并按 `references/msp/conformance.md` 产出符合性报告
   （MUST 与设计判据 D-1~D-5 全部通过才算可用；偏差必须记录）。
9. **到账确认策略必须显式选型并逐层满足不变量**（`references/payment-confirmation.md`）：
   金额指纹只是零摩擦自动化层（租约独占 INV-27、超时释放 OP-O5、尾数不进退款 INV-20）；
   截图凭证必须 `(channel, transaction_no)` 唯一绑定且歧义一律转人工；
   聚合/官方回调必须有验签 + 幂等（INV-6/7/18）。
10. **对齐成熟先例并记录差分**：对象/状态/事件语义对齐 Stripe / Lago / Kill Bill / CloudEvents / IETF（`references/msp/prior-art.md`），
    每个自研或差异点必须有"出处 + 差分 + 测试向量"。
11. **内核闭环不可改、扩展走注册点**：身份/目录/订单/支付/履约/权益/积分/退款/对账/审计是完备闭环；
    业务花样通过 `references/plugin-architecture.md` 的扩展点注入，插件只加不改、依赖单向（插件 → 内核）。
12. **个人信息与事实分离**：不可变事实（账本/事件/凭证）不得嵌入 PII；删除/掩码请求不得破坏账本可重建性
    （INV-34，见 [references/data-retention.md](references/data-retention.md)）。

## 必须显式禁止的反面模式

- 复制支付匹配域（同一笔到账被两个系统匹配 = 双花）。
- 为了"解耦"先上消息队列，却没有幂等与重放设计。
- 余额/库存直接 `UPDATE` 而无流水；退款只改订单状态。
- 金额用浮点、时间用本地时区存储。
- 把 token/密钥写进仓库、镜像层或 CI 日志。
- 阶段划分没有验收标准，或验收标准是"能编译"。
- 事件重试导致权益重复顺延（发放/续期没有按 source 幂等）。
- 金额指纹的尾数计入退款金额。
- 把金额指纹当成个人码唯一方案，不提供截图兜底（监听端挂掉时用户无法完成支付确认）。
- 截图凭证不校验流水号唯一绑定，或自动通过金额/时间/置信度不达标的歧义凭证。
- 在核心代码写插件专属分支/`switch`（应使用类型注册表与事件订阅）。
- 插件直连他人数据表、绕过账本或绕过 Entitlement 判权。

## 完成后

- 用 skill-creator 的 `scripts/quick_validate.py` 校验产出技能目录。
- 条件允许时，用独立 subagent 做一次前向测试：只给产出技能 + 一句真实需求，看它能否直接开工；把观察结果反馈回本轮生成（小步修正，不要为单次观察加通用规则）。
- 需要服务器加固/安全审计时，另行使用 `server-hardening` 技能，不要在本技能内展开。
- **把本轮新经验写回 [references/lessons-log.md](references/lessons-log.md)**（格式与去重规则见维护手册）——这是本技能持续进化的唯一入口。

## 持续进化（每次使用都必须执行）

这个技能的价值随使用次数增长，前提是每次都把新东西写回去。三条纪律：

1. **使用前**：先读 `lessons-log.md` 最近 10~15 条；如果本轮任务与某条 lesson 相关，把它带进决策。
2. **使用中/后**：把本轮出现的**新经验或决策**按格式追加到 `lessons-log.md`。素材来源包括：踩到的坑、被推翻的假设、真实成本数据、工具或版本变化、用户明确表达的偏好。
3. **提升与归档**：同主题累计 2 条以上、或直接影响"不可妥协项"时，把结论提升进 `architecture.md` / `payment-*.md` / `pitfalls.md` 正文；被证伪的条目标注 `[deprecated]` 并保留溯源，不要直接删除。

写日志的边界：

- 一条 3~6 行，写"结论 + 为什么 + 怎么落地"，不要粘贴大段代码；
- 必须标注**来源**（真实项目 / 推理产物）与**适用分支**；
- **禁止写入项目机密**：密钥、token、客户数据、内部地址。

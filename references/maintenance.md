# 技能维护手册（让本技能持续进化）

本技能的目标不是"一次写完"，而是**每次使用都变得更准**。维护动作只有四类：追加、合并、提升、废弃。

## 1. 什么时候写

满足任一条件就应在 `lessons-log.md` 追加一条：

- 踩到一个新坑（尤其是只在运行时暴露的）；
- 一个原本的判断被推翻或修正（例：以为要上消息队列，实际不需要）；
- 拿到真实成本/规模数据（部署耗时、事件量、预算）；
- 工具/版本变化导致做法改变（框架行为、云服务限制）；
- 用户明确表达的偏好或约束（预算、合规、团队习惯）。

不写：通用编程常识、能从官方文档直接查到的事实、项目机密。

## 2. 怎么写（条目模板）

```markdown
### L-编号 一句话结论（动词开头，可检索）
- 日期：YYYY-MM-DD｜来源：真实项目（哪个项目/哪次事故）｜分支：personal_qr / 任意
- 结论：<一句话，能直接指导决策>
- 为什么＋落地：<为什么会这样 + 具体怎么落地，3 行以内>
- 外部参考：<可选的成熟先例/标准引用，如 CloudEvents (id, source)、IETF 幂等草案、Stripe 状态集>
```

规则：

- 编号递增，不复用；标题是**结论**不是话题（"固定金额是长租而不是消费" > "关于订阅金额"）；
- 来源必须可追溯（真实项目 / 推理产物 / 用户口述）；
- 一条 3~6 行，不贴大段代码（需要代码就放进对应 reference 并在条目里引用）；
- 脱敏：不写密钥、token、客户数据、内部地址。

## 3. 去重与合并

追加前先按关键词搜一遍 `lessons-log.md`（例如"金额""幂等""退款""部署"）：

- 已有同主题条目 → **在原条目上补充**（追加日期与来源），不要新开一条；
- 结论冲突 → 新条目覆盖旧结论，并给旧条目加 `[deprecated by L-xxx]`，保留溯源。

## 4. 什么时候"提升"进正文

日志是候选池，正文才是规范。满足任一条件就把结论提升进对应 reference 的正文：

| 条件 | 提升到 |
| --- | --- |
| 同主题累计 ≥2 条，或直接影响"不可妥协项" | `architecture.md`（不变量/流程） |
| 与具体支付渠道强相关 | `payment-personal-qr.md` / `payment-official.md` |
| 是可复用的具体坑 | `pitfalls.md`（编号追加，不重排旧编号） |
| 改变交付顺序或验收方式 | `delivery-plan.md` |
| 表结构 / 索引层面 | `data-model.md` |

提升后**保留**日志条目（作为溯源），并在条目末尾注明"已提升至 <文件>"。

## 5. 什么时候废弃

- 外部前提变化（如接入官方网关后"金额指纹"不再必需）→ 在正文对应段落标注 `[deprecated: 原因]`，不要静默删除；
- 同一建议连续被三次实践否定 → 从"必须"降级为"可选"，并在日志里记录降级原因。

## 6. 扩展本技能的结构

- **新增支付渠道分支**：新增 `references/payment-<channel>.md`，在 `SKILL.md` 的"按收款方式读取"表里登记，并在正文给出与既有渠道的差异对照表；
- **新增业务域**（如直播、打赏、分销）：新增 `references/domain-<name>.md`，同时更新 `data-model.md` 的表目录与 `delivery-plan.md` 的阶段；
- **新增技术栈支持**（如 Node/Rust 服务端）：不改动通用参考，只在生成时把语言相关的落地方式替换掉，并在日志里记录该栈的差异经验；
- 结构变化后自检：`SKILL.md` 的路由是否仍指向存在的文件、描述是否仍能正确触发。

## 7. 同步与版本

**唯一上游：独立开源仓库 [Henri-lab/membership-system-builder](https://github.com/Henri-lab/membership-system-builder)**（2026-10-11 自 `platform-kit` 独立）。

三个位置的关系与同步方向（**上游 → 下游，单向**）：

```
Henri-lab/membership-system-builder/             # 源（唯一上游，git 版本化）
        │  rsync -a --delete（同步后在 platform-kit 提交 vendored 副本）
        ▼
platform-kit/skills/membership-system-builder/   # vendored 副本（只随上游同步，禁止直接改）
        │  rsync -a --delete
        ▼
~/.codex/skills/membership-system-builder/       # 安装副本（agent 实际加载的）
```

- 改动流程：改上游 → 提交并 push → 同步 vendored 副本
  （`rsync -a --delete <上游>/ <platform-kit>/skills/membership-system-builder/`）并在 platform-kit 提交 →
  同步安装副本（`rsync -a --delete <上游>/ ~/.codex/skills/membership-system-builder/`）；
- **不要在任何副本上直接编辑**（vendored / 安装副本 / 项目工作区临时副本），否则会出现多版本漂移；
- 每次结构变化写一条变更记录：

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v0.1.0 | 2026-10-10 | 初始版本：架构/数据模型/交付计划/支付（个人码 + 官方）/踩坑 |
| v0.2.0 | 2026-10-10 | 增加经验账本（27 条真实素材）与维护手册；SKILL.md 增加"持续进化"纪律 |
| v0.2.1 | 2026-10-10 | 技能与决策记录迁入 `platform-kit` 仓库（`skills/` + `docs/decisions.md`），确立"仓库为唯一源" |
| v0.2.2 | 2026-10-10 | 新增 L-026（入口网关独立项目）；课程站/粉丝站完成网关拆分与迁移 |
| v0.2.3 | 2026-10-10 | 新增 L-027（Next standalone 多网络绑定 0.0.0.0）；网关拆分事故复盘 |
| v0.2.4 | 2026-10-10 | 新增 L-028（网关持有自有数据卷）；清理课程站遗留 Caddy 痕迹并重新签发证书 |
| v0.3.0 | 2026-10-10 | 新增 **MSP 协议标准**（`references/msp/`：正文 + 事件契约 + 符合性判定 + 扩展机制）；SKILL.md 要求生成结果对齐 MSP 等级并产出符合性报告 |
| v0.3.1 | 2026-10-10 | 新增 `references/msp/ledger.md`（积分账本规范）；INV-23/24/25、OP-N1/N2 强化、T-26..T-30 并发与对账用例；新增 L-030 |
| v0.3.2 | 2026-10-10 | MSP 升至 v0.2.0：INV 重排为 1–27（旧 23/24/25 → 13/14/15）；新增 INV-26/27；信封对齐 CloudEvents；幂等键对齐 IETF 草案；退款状态机/段回收/quantity 语义/OP-O5 超时关单；测试向量增至 T-37；新增 `prior-art.md`、L-031~L-040、pitfalls 31–38；SKILL.md 新增 7 个决策分支 |
| v0.3.3 | 2026-10-10 | 新增 `references/plugin-architecture.md`（内核闭环 + 14 个扩展点 + 插件 manifest/生命周期/失败边界/符合性门禁，借鉴 Kill Bill/Medusa/Spree/Sylius）；architecture.md 对齐 MSP v0.2.0 并加"内核与插件边界"；extensions.md 加 §5 插件化契约；delivery-plan Phase 0 含 `extensions/` 骨架；SKILL.md 产出物加 `references/extensions.md` 与第 8/11 条；新增 L-041/L-042 |
| v0.3.4 | 2026-10-10 | 新增 `references/design-walkthrough.md`（学习资料：正常 + 边界例子 + 自测题）；OP-P2 引入 `report_grace` 宽容期（判定以 `paid_at` 为准）与 T-38；新增 L-043/L-044、pitfalls 39–40 |
| v0.4.0 | 2026-10-10 | MSP 升至 v0.3.0：新增部分退款（Refund.lines、INV-28、T-39/40）、试用与 proration（OP-T1/T2/M1、T-41~43）、拒付争议（Dispute + 权益 suspended、INV-29、T-44~46）、税务发票（TaxSnapshot/Invoice + 红冲、T-47/48）、多币种（FxSnapshot、INV-30、T-49/50）；新增 Disputes/Invoicing/MultiCurrency 符合性等级；README 候选收敛为 v0.4；新增 L-045~L-049、pitfalls 41–45 |
| v0.4.1 | 2026-10-10 | 实现侧闭环（粉丝站）：账本不可变触发器（INV-14）、发放事实表 entitlement_grants（INV-26）、定时对账 + 管理端对账/追加调整接口（T-30）、并发扣减用例（T-26）、quantity 语义修正（T-35）、gift 扩展行同事务创建 + 回填迁移；`smoke-conformance.sh` 13/13 通过；新增 L-050/L-051 |
| v0.4.2 | 2026-10-10 | 新增 `references/design-judgment.md`（加字段 vs 加对象的判定手册：六问 + 三个杀手测试 + 正反例子）；SKILL.md 学习资料登记；新增 L-052 |
| v0.4.3 | 2026-10-11 | 新增 `references/master-craft.md`（老师傅隐形知识：10 篇权威判据出处与原话、5 个评审测试、新手直觉 vs 老师傅对照表）；SKILL.md 学习资料登记；prior-art.md 加理论源头指针；新增 L-053 |
| v0.4.4 | 2026-10-11 | `payment-official.md` 新增「接入官方回调的前置条件（中国大陆）」：三条路径门槛对比、备案/属地/后缀核查方法、代码侧改造清单；新增 L-054（官方回调门槛是资质+备案，不是代码） |
| v0.4.5 | 2026-10-11 | `msp/conformance.md` 新增 §3 设计判据清单（D-1~D-5：删表重建/审计/并发同发/重放/回滚），跨等级必检且不可豁免；判定规则与章节号同步；SKILL.md 产出物与不可妥协项要求 D-1~D-5；新增 L-055 |
| v0.4.6 | 2026-10-11 | 技能独立为上游开源仓库（Henri-lab/membership-system-builder）；`platform-kit/skills/` 降级为 vendored 副本，§7 同步方向反转；L-054 隐私脱敏（移除服务器属地与域名细节）；新增 L-056 |
| v0.4.7 | 2026-10-11 | 新增 `references/payment-confirmation.md`（到账确认策略四层：金额指纹/截图凭证审核/聚合回调/官方直连 + 选型规则 + 各层不变量 + 迁移路径）；SKILL.md 新增「到账确认」分支（默认 `screenshot_review`）；conformance 新增 T-51~T-54；新增 L-057 |
| v0.4.8 | 2026-10-11 | `payment-confirmation.md` 新增 §3.5「实现要点（实战）」六条（两段式上传/内容嗅探/key 即权限/blob 预览/限额双保险/复用唯一写入口）；新增 L-058 |
| v0.4.9 | 2026-10-11 | README 现代化（badges + 质量门禁 + 起源与署名 + 引用格式）；新增 `AUTHORS.md`；msp/README 加作者/上游/许可行；SKILL.md 测试向量计数更正为 54；新增 L-059 |
| v0.4.10 | 2026-10-11 | SKILL.md `description` 扩展触发面：新增「符合性审计 / 支付链路设计评审 / 协议答疑」用途与截图凭证审核、聚合服务商等新分支 |
| v0.4.11 | 2026-10-11 | 新增 GitHub Actions 校验工作流（frontmatter / 内部链接 / L 编号唯一 / T 编号唯一连续 / agents 描述长度 / 待办标记扫描）与 `scripts/validate_skill.py`；README 加 CI badge |
| v0.4.12 | 2026-10-11 | 新增 `assets/conformance-smoke.sh.tmpl`（T-02/03/04/26/27/33/36/40/52 + D-1 的可执行验收骨架）；conformance §4 与 SKILL.md 产出物链接模板；新增 L-060 |
| v0.4.13 | 2026-10-11 | spec 新增 INV-31（支付意图并发上限）与 INV-32（撞码限速告警）、错误码 `TOO_MANY_ATTEMPTS`；conformance 新增 T-55/T-56 与 MUST 项；新增 L-061 |
| v0.4.14 | 2026-10-11 | spec 新增 OP-R3 `attachTransferEvidence`（人工转账回执）与 INV-33；events 新增 `refund.transfer_attached`；data-model 新增 `refund_transfer_evidences`；conformance 新增 T-57/T-58；新增 L-062 |
| v0.4.15 | 2026-10-11 | 新增 `references/data-retention.md`（三类数据 / 保留期 / 删除权与只追加账本共存 / 删除请求流程 / 隐私红线）；spec 新增 INV-34；conformance 新增 T-59/T-60；SKILL.md 始终读取登记；新增 L-063 |
| v0.4.16 | 2026-10-11 | 新增 `references/reminder-contract.md`（提醒语义分层 / 窗口幂等键 / 渠道降级 / 退订隔离 / 失败重试）；spec 新增 INV-35；events 新增 `reminder.sent/skipped`；data-model 扩展提醒表；conformance 新增 T-61/T-62；新增 L-064 |
| v0.4.17 | 2026-10-11 | 新增 `references/account-merge.md`（合并语义：段并集 / 账本 transfer / 不可逆）；spec 新增 §4.8 OP-M2 与 INV-36；events 新增 `account.merged`；data-model 新增 `account_merges`；conformance 新增 T-63/T-64；新增 L-065 |
| v0.5.0 | 2026-10-11 | **MSP 升至 v0.4.0**（第二梯队收尾）：请求侧节流、人工转账回执、数据保留与删除、续费提醒契约、账户合并（INV-31~36、OP-R3/M2、T-55~64）；SKILL.md 不可妥协项 12 条；README 候选收敛（剩余：埋点与画像）；prior-art 补行 |
| v0.5.1 | 2026-10-14 | 新增 `references/solution-tiers.md`（选型访谈：目的×规模×硬约束 / 档位矩阵 L0~L3 / 换档触发器 / 理由模板）；SKILL.md 第一步改为「必做访谈 → 按档位落分支」，禁止静默默认；始终读取与产出物要求同步；新增 L-066 |
| v0.5.2 | 2026-10-14 | MSP spec §1 新增「身份边界」声明（principal 由 ASP 签发、业务层不自造）；认证独立为 identity-system-builder（ASP v0.1.0）；solution-tiers 与 SKILL.md 账号体系分支接线；新增 L-067 |
| v0.5.3 | 2026-10-17 | 课程站 bug-log 复盘回填：新增 L-068（跨模块状态机一起收口：订单关闭显式释放支付单与金额占用） |
| v0.5.4 | 2026-10-18 | MSP 升至 v0.4.1：spec 新增 §10 幂等键规范（键随重复源/原子占位与结果回放/幂等≠业务唯一性/状态机条件更新/全操作防重地图/常见坑）；conformance 新增 T-65/T-66 与 MUST 项；新增 L-069 |
| v0.5.5 | 2026-10-18 | 新增 `references/outbox.md`（Outbox 实现机制唯一权威：三板斧/领取与退避/死信闭环/吞吐与延迟/消费端幂等/观测/测试/升级信号）；SKILL.md 与 msp/README 登记；spec INV-18 加指针；新增 L-070 |
| v0.5.6 | 2026-10-18 | spec §10.1 补客户端意图键生命周期（idle/in-flight/换新 + 会话级存储 + 服务端作用域与保留期 + 业务相似单检测边界）；新增 L-071；工程坑 E-114 进 engineering-pitfalls |
| v0.5.7 | 2026-10-18 | outbox.md 补「同库独立表是硬约束」（事务边界/独立表理由/每服务一张/CDC 混合例外）+ schema version/按月分区/最老 pending age 告警/graceful drain + 反模式 9/10；新增 L-072 |
| v0.5.8 | 2026-10-18 | outbox.md 新增 §13 拓扑与角色（四角色失败域 / 直连 vs 经 MQ 两种形态 / 信封端到端 / aggregate_id 分区键 / microservices.io·MassTransit·Watermill 对照）；prior-art 补行；新增 L-073 |
| v0.5.9 | 2026-10-18 | outbox.md 新增 §13.1（relay 双重身份 / outbox 与 MQ 接力分工表 / 直连代价四条 / 消费者直扫 outbox 的中间玩法 / 一句话分流）；L-073 补充 |

## 8. 自检清单（每次改完技能跑一遍）

1. frontmatter 的 `name` 与目录名一致、`description` 仍能区分适用场景；
2. `SKILL.md` 里引用的每个文件都存在，且路由描述与实际内容一致；
3. 没有未完成的待办标记；
4. `agents/openai.yaml` 的 `short_description` 在 25~64 字符之间；
5. 新增条目遵守格式、已去重、未包含机密；
6. 工作区副本已同步到 `~/.codex/skills/`。
7. 新增原则/概念前查 agent-skills-index 的 `concept-map.md`：已有则引用不复制，新概念先登记权威位置。

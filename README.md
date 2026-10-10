# membership-system-builder 🛡️ 会员订阅支付系统构建器

> A **Codex skill** that turns "membership + paid content + payments" into a reviewed,
> step-by-step, verifiable build plan that any capable agent can execute from zero —
> independent of language, framework, and middleware.
> Docs are in Chinese; the core protocol (MSP) is tool-neutral.

<p align="center">
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/License-MIT-blue.svg"></a>
  <img alt="MSP v0.3.0" src="https://img.shields.io/badge/protocol-MSP%20v0.3.0-blueviolet">
  <img alt="Conformance" src="https://img.shields.io/badge/conformance-T01--T54_%2B_D1--D5-success">
  <img alt="Version" src="https://img.shields.io/badge/version-v0.4.9-informational">
  <a href="https://github.com/Henri-lab/membership-system-builder"><img alt="GitHub stars" src="https://img.shields.io/github/stars/Henri-lab/membership-system-builder?style=social"></a>
</p>

把「会员订阅 + 付费内容 + 支付」做成一份**可直接执行的构建技能**：任何代码能力达标的 agent
读它就能从零搭出可理解、可维护、可演进的系统。既覆盖个人收款码起步的小站，也覆盖官方网关、
订阅周期、积分、礼物、周边、退款、拒付争议、税务发票与多币种。

## 快速开始

```bash
mkdir -p ~/.codex/skills
git clone https://github.com/Henri-lab/membership-system-builder.git ~/.codex/skills/membership-system-builder
```

之后在任意 Codex 会话中按 skill 名（`membership-system-builder`）触发即可。
本仓库是该技能的唯一上游；历史项目 `platform-kit` 内保留的 `skills/membership-system-builder/`
是 vendored 副本，改动只在本仓库进行。

## 目录

```text
SKILL.md                 主入口：选型分支 → 按分支读参考 → 生成目标项目技能
agents/openai.yaml       agent 元数据
assets/                  生成产物模板（generated-skill-template）
references/
├── msp/                 MSP 协议 v0.3.0（规范性）：spec / ledger / events / conformance / extensions / prior-art
├── architecture.md      参考架构与不可妥协项
├── data-model.md        表目录与关键约束
├── delivery-plan.md     阶段划分与验收标准
├── plugin-architecture.md  内核闭环 + 插件注入扩展点
├── payment-confirmation.md  到账确认策略四层（指纹 / 截图审核 / 聚合回调 / 官方直连）
├── payment-personal-qr.md / payment-official.md  两种收款方式的完整链路
├── pitfalls.md / lessons-log.md  真实踩坑与经验账本
├── maintenance.md       技能持续进化纪律
└── design-walkthrough.md / design-judgment.md / master-craft.md  学习资料
```

## 三个不寻常之处

1. **协议而非模板**：MSP 只规定外部可观察的行为与不变量，不规定表名/框架/中间件；
   用 54 条测试向量（T-01~T-54）+ 5 条设计判据（D-1~D-5：删表重建/审计/并发同发/重放/回滚）判定「可用」。
2. **到账确认策略分层**：无回调场景不靠单一路径——金额指纹自动快车道、截图凭证 OCR/人工审核
   （离线 hook）、聚合服务商与官方回调；每层都有强制不变量与迁移路径。
3. **持续进化纪律**：`lessons-log.md` 追加经验、`maintenance.md` 决定合并/提升/废弃，技能越用越准。

## 质量门禁

| 维度 | 内容 |
| --- | --- |
| 符合性等级 | Core / Subscriptions / Points / Gifts / Physical / Disputes / Invoicing / MultiCurrency |
| 行为验收 | T-01~T-54 测试向量（并发、重放、退款、争议、发票、多币种……） |
| 设计判据 | D-1~D-5（删表重建 / 审计 / 并发同发 / 重放 / 回滚），跨等级不可豁免 |
| 不可妥协项 | 11 条（单一判权源、账本唯一事实来源、金额指纹租约独占……） |

## 起源与署名

本技能于 2026-10-10 在私有项目 `platform-kit` 中沉淀（真实踩坑 + 对抗性评审），
2026-10-11 独立为公开仓库。设计评审与文档撰写由 AI（Codex）辅助完成，
经验账本每条都保留来源署名；作者清单见 [AUTHORS.md](AUTHORS.md)。

想给 credit 时，按下面的引用格式即可；二次分发必须保留 [LICENSE](LICENSE) 中的版权声明
（MIT 的法定要求）：

```text
membership-system-builder（MSP v0.3.0）
作者：henrifox
仓库：https://github.com/Henri-lab/membership-system-builder
首发：2026-10-10（platform-kit）｜独立开源：2026-10-11
许可：MIT（保留署名）
```

## 参与方式

按 [references/maintenance.md](references/maintenance.md) 的规则贡献：
经验按 L-xxx 追加（注明来源与分支）、同主题合并、结论提升进正文、被证伪的标注废弃。
新主题按「加法原则」扩展（见 `references/msp/extensions.md`），不修改既有语义。

## License

[MIT](LICENSE) © 2026 henrifox

# 到账确认策略分层（payment confirmation ladder）

> 适用：`personal_qr` 与一切"没有回调 hook"的收款渠道。回答核心问题：
> **"没有 hook 时，怎么确认『这笔钱就是这个人、为这笔订单付的』？"**
> 配套阅读：[payment-personal-qr.md](payment-personal-qr.md)（金额指纹实现细节）、
> [payment-official.md](payment-official.md)（聚合服务商与官方回调）。

## 0. 一句话

确认策略按**证据强度**分四层。证据强度 = 能否回答"谁、什么时候、为哪笔订单、付了多少钱"；
**自动化程度只是第二优先级**。金额指纹是零摩擦快车道，不是唯一方案；截图凭证 + OCR + 人工审核
才是个人码场景下最接近"离线 hook"的方案。

```
Tier 0 金额指纹（自动）        身份盲，金额空间碰撞风险
Tier 1 截图凭证 + OCR + 审核    绑定流水号/付款人/时间 = 离线 hook
Tier 2 聚合服务商 webhook       无自有备案的准官方回调
Tier 3 官方直连 webhook         全自动化 + API 退款
```

## 1. 四层对照表

| 维度 | Tier 0 金额指纹 | Tier 1 截图 + 审核 | Tier 2 聚合服务商 | Tier 3 官方直连 |
| --- | --- | --- | --- | --- |
| 证据 | 金额 + 监听来源签名 | 流水号/付款人/金额/时间 | 渠道回调（验签） | 渠道回调（验签） |
| 能否知道付款人 | 否 | 是（昵称 / 账号尾号） | 部分 | 是 |
| 自动化 | 全自动 | OCR 自动 + 歧义人工 | 全自动 | 全自动 |
| 用户摩擦 | 无 | 付款后上传截图 | 无 | 无 |
| 单日订单量上限 | 金额空间（默认 99 分位） | 审核人力 | 高 | 高 |
| 前置条件 | 无 | 无 | 服务商进件（部分支持小微） | 执照 + ICP 备案 + 域名 |
| 伪造/欺诈风险 | 撞码、监听被绕 | 截图可伪造（需核验） | 低 | 低 |
| 退款 | 人工转账 + 工单冲销 | 人工转账 + 工单冲销 | API / 人工 | API |

## 2. 选型规则

1. 有执照 + 备案域名 → **Tier 3**；
2. 没有备案、想接回调 → **Tier 2**（先做进件可行性核查，见 payment-official.md §接入官方回调的前置条件）；
3. 个人码 + 单量少 + 有人工 → **Tier 1 为主、Tier 0 做自动快车道**（hybrid）；
4. 个人码 + 想零人力 → **Tier 0**，但必须完整实现本层全部不变量，并接受"付款人不可知"的风险；
5. 决策顺序：**证据强度优先于自动化**；任何自动路径必须留可审计证据，任何歧义必须转人工。

SKILL.md 分支取值：`amount_fingerprint` / `screenshot_review` / `hybrid` / `aggregation_webhook`，默认 `screenshot_review`。

## 3. Tier 1 截图凭证确认（个人码推荐主方案）

### 3.1 流程

1. 用户下单 → 展示收款码 + 明确提示"付款后截图上传"；
2. 用户付款并上传截图（支持多张）；
3. OCR 提取：流水号 `transaction_no`、金额、付款时间、付款人昵称/账号尾号；
4. 自动核验：`(channel, transaction_no)` 未被占用 + 金额 = 订单应付 + 付款时间在窗口内 + OCR 高置信 → 可自动通过；否则 `pending_review`；
5. 人工审核：比对截图原文、OCR 结果与订单；`approve` → 走 OP-P5 履约路径；`reject` → 关闭凭证，订单保持 `pending` 或走补单；
6. 超时未上传 → 订单按 OP-O5 关闭、释放占用；用户仍可自助补单。

### 3.2 凭证模型（最小字段）

```sql
create table payment_evidences (
  id              uuid primary key default gen_random_uuid(),
  order_id        uuid not null references orders(id),
  user_id         uuid not null references users(id),
  channel         text not null,              -- wechat / alipay / ...
  transaction_no  text not null,              -- 流水号（离线 hook 的身份）
  amount_cents    bigint not null,
  paid_at         timestamptz not null,
  payer_label     text,                       -- 付款人昵称 / 账号尾号
  evidence_urls   text[] not null,
  ocr_raw         jsonb,                      -- 原始 OCR 结果，审核后不可变
  status          text not null default 'pending_review'
                  check (status in ('pending_review','approved','rejected','duplicate')),
  reviewer        text, reviewed_at timestamptz, review_note text,
  created_at      timestamptz not null default now()
);
create unique index uq_evidence_txn on payment_evidences (channel, transaction_no);
```

### 3.3 强制不变量（MUST）

- **E1 凭证不可变**：审核后不得修改 OCR 结果与原始截图引用；纠错 = 新记录 / 驳回重传；
- **E2 流水号唯一绑定**：`(channel, transaction_no)` 全局唯一，冲突 → `duplicate`，不得绑定第二个订单；
- **E3 歧义不自动履约**：金额不符 / 时间出窗 / OCR 低置信 / 疑似重复 → 一律 `pending_review`；
- **E4 审核留痕**：`approve` / `reject` 必须记录 `reviewer + reason + reviewed_at`（INV-24）；
  `approve` 必须走与自动匹配**完全相同**的履约路径（OP-P5），不得另开旁路；
- **E5 时间权威**：以付款时刻 `paid_at` 校验服务端时间窗（INV-21），不信任任何用户声明；
- **E6 自动通过门槛**：只允许"高置信 + 流水号唯一 + 金额时间吻合"三者同时满足；其余全转人工。

### 3.4 反伪造（按单量升级）

- 单量小：人工肉眼比对截图（支付应用 UI 特征、时间、流水号位数）；
- 单量中：OCR 置信度 + 与监听端流水交叉核对（有 Tier 0 时）+ 上传元数据（时间/机型）一致性；
- 单量大：接 Tier 2/3 回调做权威核对，截图降级为兜底。
- 底线认知：截图永远不是"渠道权威"，它是**离线 hook**；只要伪造开始有利可图，就必须向 Tier 2/3 迁移。

### 3.5 实现要点（实战）

来自一次真实落地（个人码 + 截图审核主链，含端到端验收）——流程好设计，坑都在这六处：

1. **两段式提交**：截图先上传拿到**站内相对地址**，再随凭证提交进 `evidence_urls`；
   不要做成"填截图外链"——用户没有图床，外链还绕过了你自己的权限与事后审计。
2. **类型按内容嗅探**：用前 512 字节（如 `http.DetectContentType`）决定扩展名与 MIME，
   **绝不信任文件名与客户端 `Content-Type`**，否则能把 HTML 伪装成 `.png` 存进来。
3. **key 即权限**：存储 key 用 `claims/<userID>/<yyyymmdd>/<random>.<ext>`——路径前缀本身就是归属声明，
   读取时按前缀判 owner、管理员放行，同时统一 `path.Clean` + 拒绝 `..` 做防穿越。
4. **预览不开公开地址**：站内凭证用带 `Authorization` 的 fetch 拉成 blob 给 `<img>`，
   不引入公开 URL、也不需要签名地址；用户自己的预览用本地 objectURL，不必回传服务器。
5. **限额双保险**：请求侧 `MaxBytesReader` + 读取侧 `LimitReader(上限+1)`，
   错误码分层（413 过大 / 415 类型 / 403 越权 / 404 不存在），前端才能给出可读提示。
6. **审核复用唯一写入口**：`approve` 直接走既有凭证审核（订单转 paid → `order.paid` → outbox 异步发权益），
   不新增第二条履约路径。金额指纹**保留**——它是审核时的防撞码（同窗口内多单金额互不相同），不是监听端的专属。

AI 预审的落点很小：凭证表加 JSONB `ai_review` + 一个异步 worker + 可替换的 `VisionProvider` 接口
（key 走环境变量）；默认**只写建议**（建议值 + 置信度），阈值开关跑稳后再放开自动通过。

## 4. Tier 0 金额指纹（自动快车道）

实现细节全部在 [payment-personal-qr.md](payment-personal-qr.md)。在本分层里它承担：自动命中 → 直接履约；
未命中 / 歧义 → 引导截图或人工。必须满足：租约独占（INV-27）、超时释放（OP-O5）、
尾数不进退款（INV-20）、通知两层防线（nonce 防重放 + 结构化幂等键）。

**身份盲是本层固有缺陷**：它回答"哪笔钱到账了"，回答不了"是谁付的"——因此它适合做快车道，不适合做唯一方案。

## 5. 混合模式（hybrid，个人码推荐）

- 支付窗口内：监听端自动匹配指纹 → 成功即履约（零摩擦）；
- 监听端挂掉 / 金额歧义：自动给用户推送"上传截图"入口；
- OCR 自动核验通过 → 履约；否则进人工队列；
- 保证：**同一条到账最多被一个策略履约一次**——各策略共享唯一键
  （金额占用 / `(channel, transaction_no)` / 通知 nonce，见 ledger.md 的幂等分层）。

## 6. Tier 2 / 3 回调

见 [payment-official.md](payment-official.md)。要点：验签（HMAC / RSA2 / 证书）、5 秒内返回、
`(provider, provider_ref)` 幂等、资金与事件同事务（INV-18）。
Tier 2 只是把"回调前置条件"外包给服务商，核心契约与 Tier 3 相同——业务代码不感知差异。

## 7. 迁移路径（不重写内核）

```
Tier 0/1 → Tier 2 → Tier 3
```

每次升级只换 Provider 适配器与确认策略实现；订单 / 权益 / 账本 / 退款内核不动（INV-6 保持"唯一写入口"）。
hook 上线后，金额指纹按 maintenance.md §5 规则标注 `[deprecated]` 退役，历史数据保留只读。

## 8. 符合性

- 截图策略的新测试向量：T-51~T-54（conformance.md §4）与 MUST 检查项（conformance.md §2 资金与订单）；
- 策略分层不改变 MSP 符合性等级；截图凭证确认是 Core 等级的确认策略选项之一。

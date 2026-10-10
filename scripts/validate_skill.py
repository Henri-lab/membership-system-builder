#!/usr/bin/env python3
"""membership-system-builder 仓库自检（本地与 CI 通用）。

检查项：
1. SKILL.md frontmatter：name 与目录名一致、description 非空；
2. 所有 Markdown 内部链接可解析；
3. lessons-log.md 的 L-xxx 编号唯一；
4. conformance.md 的 T-xx 编号唯一且连续；
5. agents/openai.yaml 的 short_description 在 25~64 字符；
6. 无 TODO / FIXME 占位。

用法：python3 scripts/validate_skill.py [skill目录，默认当前目录]
"""

import re
import sys
from pathlib import Path

try:
    import yaml  # type: ignore
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

errors: list[str] = []
warnings: list[str] = []


def frontmatter(text: str) -> tuple[dict, str]:
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not m:
        return {}, ""
    body = m.group(1)
    if HAS_YAML:
        data = yaml.safe_load(body) or {}
        return data, body
    data = {}
    for key in ("name", "description"):
        km = re.search(rf"^{key}:\s*(.+)$", body, re.M)
        if km:
            data[key] = km.group(1).strip().strip('"').strip("'")
    return data, body


root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()

# 1. frontmatter
skill_md = root / "SKILL.md"
if not skill_md.exists():
    errors.append("SKILL.md 不存在")
else:
    data, _ = frontmatter(skill_md.read_text(encoding="utf-8"))
    if data.get("name") != root.name:
        errors.append(f"frontmatter name={data.get('name')!r} 与目录名 {root.name!r} 不一致")
    if not data.get("description"):
        errors.append("frontmatter description 为空")

# 2. 内部链接
link_re = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
for md in sorted(root.rglob("*.md")):
    text = md.read_text(encoding="utf-8")
    for target in link_re.findall(text):
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        path = target.partition("#")[0]
        if path and not (md.parent / path).resolve().exists():
            errors.append(f"{md.relative_to(root)}: 链接失效 -> {target}")

# 3. lessons 编号唯一
lessons = root / "references" / "lessons-log.md"
if lessons.exists():
    ids = re.findall(r"^###\s+(L-\d{3})\b", lessons.read_text(encoding="utf-8"), re.M)
    dups = sorted({i for i in ids if ids.count(i) > 1})
    if dups:
        errors.append(f"lessons-log L 编号重复: {', '.join(dups)}")

# 4. conformance T 编号唯一且连续
conformance = root / "references" / "msp" / "conformance.md"
if conformance.exists():
    nums = sorted({int(n) for n in re.findall(r"\bT-(\d{2})\b", conformance.read_text(encoding="utf-8"))})
    if nums:
        expected = set(range(1, max(nums) + 1))
        missing = sorted(expected - set(nums))
        if missing:
            warnings.append(f"conformance T 编号不连续，缺: {missing}")

# 5. agents 描述长度
agents = root / "agents" / "openai.yaml"
if agents.exists():
    text = agents.read_text(encoding="utf-8")
    if HAS_YAML:
        cfg = yaml.safe_load(text) or {}
        short = (cfg.get("interface") or {}).get("short_description", "")
    else:
        m = re.search(r"short_description:\s*\"([^\"]*)\"", text)
        short = m.group(1) if m else ""
    if not 25 <= len(short) <= 64:
        errors.append(f"agents/openai.yaml short_description 长度 {len(short)} 不在 25~64")

# 6. TODO/FIXME
for path in sorted(root.rglob("*")):
    if path.is_file() and ".git" not in path.parts and path.suffix in (".md", ".py", ".yml", ".yaml", ".tmpl"):
        if path.resolve() == Path(__file__).resolve():
            continue  # 校验脚本本身不参与 TODO 扫描
        text = path.read_text(encoding="utf-8", errors="ignore")
        if re.search(r"\b(TODO|FIXME)\b", text, re.I):
            errors.append(f"{path.relative_to(root)}: 含 TODO/FIXME 占位")

for w in warnings:
    print(f"WARN  {w}")
if errors:
    for e in errors:
        print(f"FAIL  {e}")
    print(f"共 {len(errors)} 个错误")
    sys.exit(1)
print("OK    技能自检通过")

#!/usr/bin/env python3
"""
bootstrap_literature_notes.py
=============================
从 _high_impact.csv 取 top N 高被引论文，按 Templates/literature-note.md
生成空骨架 Literature/@citekey.md。

只填 frontmatter（citekey/title/authors/year/venue/doi/area/citation_count），
不填预读/复述/关联（这些由用户实际读论文时让 Skill 生成）。

用法：
    python bootstrap_literature_notes.py                # 默认 top 100
    python bootstrap_literature_notes.py --top 300
    python bootstrap_literature_notes.py --dry-run
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LITERATURE = ROOT / "obsidian-vault" / "Literature"
TEMPLATE_PATH = ROOT / "obsidian-vault" / "Templates" / "literature-note.md"


def _root() -> Path:
    """返回模块级 ROOT（可在测试中 monkey-patch）。"""
    return ROOT


def _safe_id(raw: str) -> str:
    """把 DBLP-style key (含 / . 等) 转为文件系统安全的名字。

    例: conf/iccv/KirillovMRMRGXW23 -> conf_iccv_KirillovMRMRGXW23
    也把 . 替换为 _，避免 Zotero 文件名冲突。
    """
    return re.sub(r'[\\/:*?"<>|.]', "_", raw)


def load_top_n(csv_path: Path, top_n: int) -> list[dict]:
    """读 _high_impact.csv，按 citation_count 降序取前 top_n。

    处理 BOM：有些文件首列名是 '\ufeffid' 而非 'id'。
    """
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        try:
            r["_cit"] = int(r.get("citation_count") or 0)
        except ValueError:
            r["_cit"] = 0
    rows.sort(key=lambda r: r["_cit"], reverse=True)
    return rows[:top_n]


def build_note_content(template: str, row: dict) -> str:
    """按 row 替换模板里的占位区，写出空的 literature note。"""
    citekey = row.get("id", "")
    title = (row.get("title", "") or "").strip().rstrip(".")
    authors_raw = row.get("authors", "")
    # authors 是 ; 分隔，转 YAML list
    authors = [a.strip() for a in authors_raw.split(";") if a.strip()]
    year = row.get("year", "")
    venue = row.get("venue", "")
    doi = row.get("doi", "")
    area = row.get("area_folder", "")
    citation_count = row.get("citation_count", "")

    # 用纯字符串替换（模板是 Templater 友好而非 jinja）
    frontmatter = f"""---
citekey: {citekey}
title: "{_yaml_escape(title)}"
authors:
{chr(10).join(f"  - {a}" for a in authors)}
year: {year}
venue: {venue}
doi: {doi}
arxiv: {row.get("arxiv_id", "")}
zotero: ""
area: {area}
tags:
  - literature
  - status/unread
citation_count: {citation_count}
s2_paper_id: ""
---
"""

    body = template.split("---", 2)[-1] if template.count("---") >= 2 else template
    # 去除模板里 {{...}} 的 Templater 占位符，替换成实际值或保留原文骨架
    body = body.replace("{{citekey}}", citekey)
    body = body.replace("{{title}}", title)
    body = body.replace("{{authors}}", "; ".join(authors))
    body = body.replace("{{year}}", year)
    body = body.replace("{{venue}}", venue)
    body = body.replace("{{doi}}", doi)
    body = body.replace("{{arxiv}}", row.get("arxiv_id", ""))
    body = body.replace("{{zotero}}", "")
    body = body.replace("{{area}}", area)
    body = body.replace("{{citation_count}}", citation_count)
    body = body.replace("{{s2_paper_id}}", "")
    body = body.replace("{{abstract}}", row.get("tldr", "") or "（待 ZotLit 同步）")
    body = body.replace("{{annotations}}", "<!-- ZotLit 同步标注后自动填充 -->")

    return frontmatter + body


def _yaml_escape(s: str) -> str:
    """YAML 双引号字符串转义。"""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def bootstrap(top_n: int, *, dry_run: bool = False) -> dict:
    csv_path = _root() / "_high_impact.csv"
    if not csv_path.exists():
        print(f"[错误] 缺少 {csv_path}，请先跑 ccf_crawler stage1+2+3", file=sys.stderr)
        return {"error": "no _high_impact.csv"}
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    rows = load_top_n(csv_path, top_n)
    LITERATURE.mkdir(parents=True, exist_ok=True)

    generated = 0
    skipped = 0
    for row in rows:
        citekey = row.get("id", "")
        if not citekey:
            skipped += 1
            continue
        out_path = LITERATURE / f"@{_safe_id(citekey)}.md"
        if out_path.exists():
            # 不覆盖已有笔记（避免破坏 BessadokMR23 这种已填充的）
            skipped += 1
            continue
        if dry_run:
            print(f"[dry-run] {out_path.name}")
            generated += 1
            continue
        out_path.write_text(build_note_content(template, row), encoding="utf-8")
        generated += 1
    print(f"[完成] top {top_n} 中生成 {generated} 条，跳过 {skipped} 条", file=sys.stderr)
    return {"generated": generated, "skipped": skipped, "total_top_n": len(rows)}


def main() -> int:
    parser = argparse.ArgumentParser(description="批量生成 Literature Note 种子")
    parser.add_argument("--top", type=int, default=100, help="取 top N 高被引论文")
    parser.add_argument("--dry-run", action="store_true", help="只列出将生成的文件，不写盘")
    args = parser.parse_args()
    result = bootstrap(args.top, dry_run=args.dry_run)
    print(json.dumps_safe(result) if False else str(result))
    return 0


# 简易 json 兜底
import json  # noqa: E402


def json_dumps_safe(obj):
    return json.dumps(obj, ensure_ascii=False)


# 重写 main 用正确的 json 输出
def main_v2() -> int:
    parser = argparse.ArgumentParser(description="批量生成 Literature Note 种子")
    parser.add_argument("--top", type=int, default=100)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = bootstrap(args.top, dry_run=args.dry_run)
    print(json_dumps_safe(result))
    return 0


if __name__ == "__main__":
    sys.exit(main_v2())
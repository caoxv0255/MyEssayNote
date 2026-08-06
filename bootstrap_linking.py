#!/usr/bin/env python3
"""
bootstrap_linking.py
====================
为 _high_impact.csv 中 top N 高被引论文的 literature note，注入
linking-paper-concepts 同源 + 同人两条纯本地关联，写入 `## 关联` 区。

这是 linking-paper-concepts skill 的本地降级实现（S2 限速时也可用）：
  - 同源：同 venue + 同 year
  - 同人：共享一作 family name
  （同引、同义路依赖 S2，本脚本跳过，由用户后续手跑）

用法：
    python bootstrap_linking.py                # 默认 top 30
    python bootstrap_linking.py --top 100
    python bootstrap_linking.py --dry-run
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LITERATURE = ROOT / "obsidian-vault" / "Literature"
HIGH_IMPACT = ROOT / "_high_impact.csv"


def _safe_id(raw: str) -> str:
    return re.sub(r'[\\/:*?"<>|.]', "_", raw)


def load_top_n(top_n: int) -> list[dict]:
    with open(HIGH_IMPACT, "r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        try:
            r["_cit"] = int(r.get("citation_count") or 0)
        except ValueError:
            r["_cit"] = 0
    rows.sort(key=lambda r: r["_cit"], reverse=True)
    return rows[:top_n]


def first_author_family(authors_str: str) -> str:
    """从 '; ' 分隔的 authors 串提一作 family name。"""
    if not authors_str:
        return ""
    first = authors_str.split(";", 1)[0].strip()
    # DBLP style: "Jiahao Xie 0001" -> family="Xie"
    # 也兼容 "Xie, Jiahao"
    if "," in first:
        first = first.split(",", 1)[0].strip()
    parts = first.split()
    if not parts:
        return ""
    # 跳过数字后缀
    name_parts = [p for p in parts if not re.fullmatch(r"\d+", p)]
    if not name_parts:
        return ""
    # 假设 family name 是最后一个 token
    return name_parts[-1].lower()


def find_candidates_same_venue_year(focal: dict, all_rows: list[dict]) -> list[dict]:
    """同源（同 venue + 同 year），按 citation 降序，最多 8 条。"""
    cands = [
        r for r in all_rows
        if r.get("venue") == focal.get("venue")
        and r.get("year") == focal.get("year")
        and r.get("id") != focal.get("id")
    ]
    cands.sort(key=lambda r: r.get("_cit", 0), reverse=True)
    return cands[:8]


def find_candidates_same_first_author(focal: dict, all_rows: list[dict]) -> list[dict]:
    """同人（共享一作 family name），按 year desc + citation desc，最多 8 条。"""
    focal_family = first_author_family(focal.get("authors", ""))
    if not focal_family:
        return []
    cands = []
    for r in all_rows:
        if r.get("id") == focal.get("id"):
            continue
        family = first_author_family(r.get("authors", ""))
        if family and family == focal_family:
            cands.append(r)
    cands.sort(key=lambda r: (-int(r.get("year", 0) or 0), -r.get("_cit", 0)))
    return cands[:8]


def render_wikilinks(focal: dict, candidates: list[dict], channel: str) -> list[str]:
    """渲染 wikilink 列表。"""
    lines = []
    for c in candidates:
        ck = c.get("id", "")
        title = (c.get("title") or "")[:60]
        year = c.get("year", "")
        venue = c.get("venue", "")
        if channel == "同源":
            reason = f"同源: 同发表于 {venue} ({year})"
        elif channel == "同人":
            family = first_author_family(c.get("authors", ""))
            reason = f"同人: 共享一作 {family.capitalize()}"
        else:
            reason = channel
        lines.append(f"- [[@{_safe_id(ck)}]] — {reason}。")
    return lines


def inject_relations(focal: dict, candidates_same_vy: list[dict],
                     candidates_same_author: list[dict], *,
                     dry_run: bool = False) -> dict:
    """将关联行写入 literature note 的 ## 关联 段。

    幂等：每次运行先清除旧的"自动生成"块，再写入新的。"""
    note_path = LITERATURE / f"@{_safe_id(focal.get('id', ''))}.md"
    if not note_path.exists():
        return {"status": "NO_NOTE", "note": str(note_path)}

    content = note_path.read_text(encoding="utf-8")
    if "## 关联" not in content:
        return {"status": "NO_SECTION", "note": str(note_path)}

    # 渲染两条关联
    lines = ["", "### 自动生成（bootstrap_linking.py）", ""]
    lines.append("**同源（同 venue 同 year）**:")
    same_vy_lines = render_wikilinks(focal, candidates_same_vy, "同源")
    if same_vy_lines:
        lines.extend(same_vy_lines)
    else:
        lines.append("（无候选）")
    lines.append("")
    lines.append("**同人（共享一作）**:")
    same_author_lines = render_wikilinks(focal, candidates_same_author, "同人")
    if same_author_lines:
        lines.extend(same_author_lines)
    else:
        lines.append("（无候选）")
    lines.append("")

    block = "\n".join(lines)

    if dry_run:
        return {
            "status": "DRY_RUN",
            "note": str(note_path),
            "same_vy": len(candidates_same_vy),
            "same_author": len(candidates_same_author),
        }

    # 1. 先清除已有的 "### 自动生成（bootstrap_linking.py）" 块
    auto_marker = "### 自动生成（bootstrap_linking.py）"
    # 找到第一个出现位置
    auto_idx = content.find(auto_marker)
    if auto_idx >= 0:
        # 从 auto_idx 之前的最后两个换行符往前找（保持段落整洁）
        # 简化：直接切到下一个 ## 或文末
        next_section = content.find("\n## ", auto_idx)
        if next_section < 0:
            content = content[:auto_idx].rstrip() + "\n"
        else:
            content = content[:auto_idx].rstrip() + "\n" + content[next_section:]

    # 2. 在 ## 关联 后插入新 block
    marker = "## 关联"
    idx = content.find(marker)
    if idx < 0:
        return {"status": "NO_SECTION", "note": str(note_path)}
    after_marker = idx + len(marker)
    # 找到下一个 ## 或文件末尾
    next_section = content.find("\n## ", after_marker)
    if next_section < 0:
        new_content = content.rstrip() + "\n" + block
    else:
        new_content = content[:next_section].rstrip() + "\n" + block + "\n" + content[next_section:]

    note_path.write_text(new_content, encoding="utf-8")
    return {
        "status": "WRITTEN",
        "note": str(note_path),
        "same_vy": len(candidates_same_vy),
        "same_author": len(candidates_same_author),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="为 top N 论文注入同源+同人关联")
    parser.add_argument("--top", type=int, default=30)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    rows = load_top_n(args.top)
    print(f"[bootstrap_linking] top {args.top} 论文", file=sys.stderr)

    no_note = 0
    written = 0
    for focal in rows:
        same_vy = find_candidates_same_venue_year(focal, rows)
        same_author = find_candidates_same_first_author(focal, rows)
        r = inject_relations(focal, same_vy, same_author, dry_run=args.dry_run)
        if r["status"] == "NO_NOTE":
            no_note += 1
        elif r["status"] in ("WRITTEN", "DRY_RUN"):
            written += 1

    print(f"[完成] 处理 {len(rows)} 条，注入 {written} 条关联，跳过 {no_note} 个缺失 note",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
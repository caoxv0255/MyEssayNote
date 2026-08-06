#!/usr/bin/env python3
"""
bootstrap_first_review.py
=========================
跑通第一个 lineage 产物：选 "attention mechanism" 主题，调用
tracing-lineage-by-era/resources/s2_search.py 拉取论文 → 与本地 _index.csv 合并
→ 按 5 年切片 → 抽代表作 → 调用 fact-checking-citations/resources/crossref_verify.py
反查 DOI → 写入 obsidian-vault/Reviews/attention-mechanism-lineage.md。

不依赖 S2_API_KEY：用匿名调用（脚本内置 3s 退避）。

用法：
    python bootstrap_first_review.py                # 默认 attention-mechanism
    python bootstrap_first_review.py --topic diffusion --out my-lineage.md
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent
SKILLS = ROOT / ".trae" / "skills"
S2_SEARCH = SKILLS / "tracing-lineage-by-era" / "resources" / "s2_search.py"
CROSSREF = SKILLS / "fact-checking-citations" / "resources" / "crossref_verify.py"
INDEX_CSV = ROOT / "_index.csv"
REVIEWS = ROOT / "obsidian-vault" / "Reviews"


def _slugify(topic: str) -> str:
    return topic.lower().replace(" ", "-").replace("_", "-")


def run_s2_search(topic: str, limit: int = 50) -> list[dict]:
    """调 s2_search.py 拉取主题论文（limit 默认 50 控制耗时）。"""
    cmd = [
        sys.executable,
        str(S2_SEARCH),
        topic,
        "--limit", str(limit),
        "--fields",
        "title,authors,year,venue,citationCount,externalIds,abstract,tldr",
    ]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        print("[s2_search 超时]", file=sys.stderr)
        return []
    if out.returncode != 0:
        print(f"[s2_search 失败] rc={out.returncode}", file=sys.stderr)
        print(out.stderr[:500], file=sys.stderr)
        return []
    try:
        return json.loads(out.stdout)
    except json.JSONDecodeError as e:
        print(f"[s2_search JSON 解析失败] {e}", file=sys.stderr)
        return []


def _parse_local_authors(raw: str) -> list[dict]:
    """解析 _index.csv 的 authors 字段（"A; B; C" 格式）→ S2 风格 [{"name": "..."}]"""
    if not raw:
        return []
    return [{"name": a.strip()} for a in raw.split(";") if a.strip()]


def format_authors(authors) -> str:
    """渲染作者列。兼容 S2 ([{"name": "..."}]) 和字符串列表两种格式。

    单一作者直接显示, 多个作者显示 "first et al."。空 → "—"。
    """
    if not authors:
        return "—"
    if isinstance(authors[0], dict):
        names = [a.get("name", "?") for a in authors if a]
    else:
        names = [str(a) for a in authors if a]
    if not names:
        return "—"
    return f"{names[0]} et al." if len(names) > 1 else names[0]


def merge_local(s2_papers: list[dict]) -> list[dict]:
    """合并本地 _index.csv（人类维护索引）补充 PKM metadata。

    优先级 (enrichment merge, NOT overwrite):
        字段         策略
        ─────────────────────────────────────
        citekey      local 覆盖（PKM 内部 ID, 唯一例外）
        title        S2 优先, local fallback
        authors      S2 优先, local fallback
        year/venue   S2 优先（local 不参与）

    命中: citekey 来自 _index.csv.id, 缺失字段用 local 补
    未命中: 保留 S2 原始 + 合成 citekey (firstauthor{year})
    """
    doi2row: dict[str, dict] = {}
    if INDEX_CSV.exists():
        with open(INDEX_CSV, "r", encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                doi = (r.get("doi") or "").strip().lower()
                if doi:
                    doi2row[doi] = r

    merged = []
    for p in s2_papers:
        ext = p.get("externalIds") or {}
        doi = (ext.get("DOI") or "").lower()
        local = doi2row.get(doi)
        if local:
            # citekey: local 覆盖（PKM 内部 ID, 唯一例外）
            p["citekey"] = local.get("id") or p.get("citekey", "")
            p["citekey_synthesized"] = False
            # title: S2 优先, local fallback
            if not p.get("title"):
                p["title"] = local.get("title", "")
            # authors: S2 优先, local fallback
            if not p.get("authors"):
                p["authors"] = _parse_local_authors(local.get("authors", ""))
            p["_merged_from"] = "index"
        else:
            # Fallback: 合成 citekey
            authors = p.get("authors") or []
            first = ""
            if authors and isinstance(authors[0], dict):
                first = (authors[0].get("name") or "").split()[-1] or "anon"
            year = p.get("year") or "?"
            raw_ck = f"{first.lower()}{year}" if first else f"unknown{year}"
            citekey = "".join(c for c in raw_ck if c.isalnum()).lower()
            p["citekey"] = citekey
            p["citekey_synthesized"] = True
            p["_merged_from"] = "synthesized"
        merged.append(p)
    return merged


def segment_by_era(papers: list[dict], era_size: int = 5) -> dict:
    """按 5 年切片，返回 {bucket_label: [papers...]}。"""
    years = [p.get("year") for p in papers if p.get("year")]
    if not years:
        return {}
    min_year, max_year = min(years), max(years)
    buckets = defaultdict(list)
    for p in papers:
        y = p.get("year")
        if not y:
            continue
        bucket_start = min_year + ((y - min_year) // era_size) * era_size
        bucket_end = bucket_start + era_size - 1
        label = f"{bucket_start}-{bucket_end}"
        buckets[label].append(p)
    return dict(buckets)


def pick_reps(bucket_papers: list[dict], k: int = 3) -> list[dict]:
    """从 bucket 抽 top-k 代表作：按 citationCount 降序。"""
    sorted_p = sorted(bucket_papers, key=lambda p: (p.get("citationCount") or 0), reverse=True)
    return sorted_p[:k]


def verify_doi_with_crossref(doi: str) -> str:
    """调用 crossref_verify.py 返回 'VERIFIED' / 'NOT_FOUND' / 'ERROR' / 'UNKNOWN'。"""
    if not CROSSREF.exists():
        return "UNKNOWN"
    try:
        out = subprocess.run(
            [sys.executable, str(CROSSREF), doi],
            capture_output=True, text=True, timeout=30,
        )
    except subprocess.TimeoutExpired:
        return "ERROR"
    if out.returncode != 0:
        return "ERROR"
    try:
        data = json.loads(out.stdout)
        return data.get("status", "UNKNOWN")
    except json.JSONDecodeError:
        return "UNKNOWN"


def render_lineage(topic: str, papers: list[dict], buckets: dict) -> str:
    """渲染 Markdown lineage 文档。"""
    slug = _slugify(topic)
    verified_count = 0
    fail_count = 0

    lines = [
        "---",
        "type: review",
        "topic: " + slug,
        f"generated_by: bootstrap_first_review.py",
        f"paper_count: {len(papers)}",
        f"source: semantic_scholar + local_index",
        "fact_check_status: partial",
        "---",
        "",
        f"# 分年代脉络：{topic}",
        "",
        f"> 自动生成的 lineage 骨架；总拉取 {len(papers)} 篇，按 {len(buckets)} 个年代桶分段。",
        "",
        "## 概览",
        f"- 总论文数：{len(papers)}",
        f"- 年代范围：{min((p.get('year') or 0) for p in papers if p.get('year'))}-"
        f"{max((p.get('year') or 0) for p in papers if p.get('year'))}",
        f"- 年代桶数：{len(buckets)}",
        "",
        "## 年代桶",
        "",
    ]

    for label in sorted(buckets.keys()):
        bucket = buckets[label]
        reps = pick_reps(bucket, k=3)
        lines.append(f"### {label}（{len(bucket)} 篇）")
        lines.append("")
        lines.append("| Citekey | 作者 | 标题 | 年份 | 引用 | DOI 状态 |")
        lines.append("|---|---|---|---|---|---|")
        for p in reps:
            ck = p.get("citekey", "?")
            authors_str = format_authors(p.get("authors"))
            title = (p.get("title") or "")[:60]
            year = p.get("year", "?")
            cit = p.get("citationCount") or 0
            ext = p.get("externalIds") or {}
            doi = ext.get("DOI") or ""
            doi_status = verify_doi_with_crossref(doi) if doi else "无 DOI"
            if doi_status == "VERIFIED":
                verified_count += 1
            elif doi_status in ("NOT_FOUND", "ERROR"):
                fail_count += 1
            doi_cell = doi if doi else "—"
            if doi_status == "VERIFIED":
                doi_cell += " ✅"
            elif doi_status == "NOT_FOUND":
                doi_cell += " ❌"
            synth = " (合成)" if p.get("citekey_synthesized") else ""
            lines.append(f"| [[{ck}]]{synth} | {authors_str} | {title} | {year} | {cit} | {doi_cell} |")
        lines.append("")

    lines.extend([
        "## 脉络依据",
        "",
        f"- Semantic Scholar 主题检索（topic=`{topic}`）",
        f"- 本地 _index.csv 合并（按 DOI 匹配生成 citekey）",
        f"- Crossref 反查：✅ {verified_count} / ❌ {fail_count} / 其他 {len(papers) - verified_count - fail_count}",
        "",
        "## 引用反查记录",
        "",
        "（已在上表的 DOI 状态列中体现每篇代表作的反查结果）",
        "",
        "> 自动生成，可能包含合成 citekey（首次合并时本地无对应记录）。",
        "> 建议在 Obsidian 中手工核对 `## 脉络依据` 中的合成 citekey 是否需要替换。",
    ])
    return "\n".join(lines)


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成第一个 lineage 产物")
    parser.add_argument("--topic", default="attention mechanism")
    parser.add_argument("--limit", type=int, default=50, help="S2 拉取上限")
    parser.add_argument("--out", default=None, help="输出文件名（默认 <topic>-lineage.md）")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--from-local", action="store_true",
                        help="S2 不可用时降级：仅用本地 _high_impact.csv + _abstracts.jsonl，"
                             "按 title 关键词过滤")
    return parser.parse_args(argv)


def _load_local_corpus(topic: str, limit: int) -> list[dict]:
    """S2 降级路径：从 _high_impact.csv + _abstracts.jsonl 读 title 关键词匹配的论文。"""
    hi = ROOT / "_high_impact.csv"
    abs_jsonl = ROOT / "_abstracts.jsonl"
    if not hi.exists():
        return []
    with open(hi, "r", encoding="utf-8-sig", newline="") as f:
        hi_rows = list(csv.DictReader(f))

    # 建 id -> abstract 索引
    abstracts: dict[str, str] = {}
    if abs_jsonl.exists():
        with open(abs_jsonl, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    obj = json.loads(line)
                    abstracts[obj.get("id", "")] = obj.get("abstract", "")
                except json.JSONDecodeError:
                    continue

    topic_tokens = [t.lower() for t in topic.split() if len(t) > 2]
    corpus = []
    for row in hi_rows:
        title = (row.get("title") or "").lower()
        abs_text = abstracts.get(row.get("id", ""), "").lower()
        # 命中条件：title 含至少一个 token，或 abstract 含至少一个 token
        hit = any(tok in title for tok in topic_tokens) or any(tok in abs_text for tok in topic_tokens)
        if not hit:
            continue
        try:
            cit = int(row.get("citation_count") or 0)
        except ValueError:
            cit = 0
        corpus.append({
            "externalIds": {"DOI": row.get("doi", "")},
            "title": row.get("title", ""),
            "year": int(row.get("year", 0) or 0),
            "venue": row.get("venue", ""),
            "authors": [{"name": a.strip()} for a in (row.get("authors", "") or "").split(";") if a.strip()],
            "citationCount": cit,
            "abstract": abstracts.get(row.get("id", ""), ""),
            "tldr": (row.get("tldr") or "")[:300],
        })
    corpus.sort(key=lambda p: p.get("citationCount", 0), reverse=True)
    return corpus[:limit]


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)

    if not S2_SEARCH.exists():
        print(f"[错误] 缺失 {S2_SEARCH}", file=sys.stderr)
        return 1

    print(f"[Step 1] 拉取 topic={args.topic!r}, limit={args.limit}", file=sys.stderr)
    s2_papers = run_s2_search(args.topic, args.limit)

    if not s2_papers:
        if args.from_local:
            print("  S2 不可用，按 --from-local 启用本地降级路径", file=sys.stderr)
            s2_papers = _load_local_corpus(args.topic, args.limit)
        else:
            print("  S2 拉取失败，启用自动降级（本地 _high_impact.csv）", file=sys.stderr)
            s2_papers = _load_local_corpus(args.topic, args.limit)
            if not s2_papers:
                print("[错误] S2 不可用且本地无匹配，请加 --from-local 强制降级或配置 S2_API_KEY", file=sys.stderr)
                return 2

    if not s2_papers:
        print("[错误] 数据源为空（S2 + 本地均无匹配）", file=sys.stderr)
        return 3
    print(f"  -> 拉到 {len(s2_papers)} 篇", file=sys.stderr)

    print(f"[Step 2] 与本地 _index.csv 合并", file=sys.stderr)
    merged = merge_local(s2_papers)
    print(f"  -> 合并后 {len(merged)} 篇", file=sys.stderr)

    print(f"[Step 3] 按 5 年切片", file=sys.stderr)
    buckets = segment_by_era(merged)
    print(f"  -> {len(buckets)} 个桶", file=sys.stderr)

    print(f"[Step 4] 渲染 Markdown + Crossref 反查", file=sys.stderr)
    md = render_lineage(args.topic, merged, buckets)

    REVIEWS.mkdir(parents=True, exist_ok=True)
    out_name = args.out or f"{_slugify(args.topic)}-lineage.md"
    out_path = REVIEWS / out_name
    if args.dry_run:
        print(f"[dry-run] 将写入 {out_path}（{len(md)} 字符）")
    else:
        out_path.write_text(md, encoding="utf-8")
        print(f"[完成] 写入 {out_path}（{len(md)} 字符）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
#!/usr/bin/env python3
"""
Semantic Scholar 引用图谱脚本（building-citation-timeline 用）
================================================================
功能：
  调用 Semantic Scholar Graph API 的 /paper/{id}/citations 与
  /paper/{id}/references 两个端点，分别获取一篇 focal paper 的：

    ① 前向引用（forward citations / 谁引用了这篇）
       —— 端点 /paper/{id}/citations，每条结果挂在 citingPaper 字段下
    ② 后向引用（backward references / 这篇引用了谁）
       —— 端点 /paper/{id}/references，每条结果挂在 citedPaper 字段下

  随后按发表年份（year）对前向、后向引用分别聚合，并标注
  influentialCitationCount 较高的"关键转折论文"候选，供上层 skill
  渲染 Mermaid timeline 使用。

  该脚本是 building-citation-timeline skill 的 Step 1 数据来源；其
  JSON 输出会被 skill 进一步加工成交互式时间线笔记，写入
  obsidian-vault\\Reviews\\{citekey}-timeline.md。

用法：
  python citation_graph.py "DOI:10.xxx" --depth 1 --limit 500
  python citation_graph.py "ArXiv:1706.03762" --depth 1 --limit 500
  python citation_graph.py "<S2 paperId>" --depth 2 --limit 500 --expand-top 10
  python citation_graph.py "DOI:10.xxx" --depth 1 --limit 500 --output graph.json

  paper_id 接受三种形式（S2 通用 ID 语法）：
    - DOI:10.xxx/yyy      （推荐，最稳定）
    - ArXiv:1706.03762
    - <40位 S2 paperId>

参数：
  --depth       引用图展开深度。1 = 仅 focal paper 的直接前向/后向引用
                （默认，推荐）；2 = 额外对每个方向 top-K 高引论文再展开
                一层。深度越大，请求数越多，越容易触发 S2 限速。
  --limit       单个方向（前向或后向）拉取的论文数上限（1..1000，默认 500）。
  --expand-top  depth>=2 时，每个方向在第 2 层展开的 top-K 高引论文数
                （默认 10）。控制二跳规模，避免请求爆炸。
  --output      JSON 输出文件路径（默认打印到 stdout）。

依赖：requests (pip install requests)
环境变量：S2_API_KEY（可选，有 key 限速更宽松：~1 req/s；无 key ~100 req/5min）

输出：JSON 对象（默认打印到 stdout；--output 指定时写入文件）。
     结构见 build_citation_graph() 的返回值文档。

注意：
  - S2 /paper/{id}/citations 与 /references 端点单页最多返回 1000 条，
    本脚本以 500 为分页步长，自动翻页直到达到 --limit 或无更多数据。
  - 字段请求统一为：
    title,year,authors,citationCount,influentialCitationCount,externalIds
    （外加 venues 便于时间线标注）。这些字段作用于嵌套的
    citingPaper / citedPaper 对象。
  - 429 限速时按指数退避重试（1s, 2s, 4s, 8s, 16s），最多 5 次。
    若 depth>=2 且持续限速，脚本会在 stderr 打印降级建议（减少深度），
    并尽量返回已拿到的部分结果，而非崩溃。
"""

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from typing import Optional

import requests

# ============ 配置 / 共享 HTTP 客户端 ============
S2_BASE = "https://api.semanticscholar.org/graph/v1"

# 共享客户端：统一 headers / DELAY / retry / Retry-After 头优先
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "_shared"))
from s2_http import API_KEY, HEADERS, DELAY, MAX_RETRIES  # noqa: E402
from s2_http import rate_limit as _rate_limit             # noqa: E402
from s2_http import request_with_retry as _request_with_retry  # noqa: E402

TIMEOUT = 30

# 嵌套论文（citingPaper / citedPaper）请求字段
# 覆盖 skill 所需的全部元数据：标题/年份/作者/引用量/影响力引用量/外部ID
PAPER_FIELDS = (
    "title,year,authors,citationCount,influentialCitationCount,"
    "externalIds,venue"
)
# focal paper 自身的字段（多要 abstract/tldr 便于时间线叙事）
FOCAL_FIELDS = (
    "title,year,authors,citationCount,influentialCitationCount,"
    "externalIds,venue,abstract,tldr,publicationDate"
)

# 单页条数（S2 /citations、/references 单页硬上限 1000，取 500 兼顾稳定）
PAGE_SIZE = 500
# 单方向允许拉取的绝对上限
HARD_CAP = 1000
# depth>=2 时每方向展开的 top-K（防请求爆炸）
DEFAULT_EXPAND_TOP = 10


def _normalize_paper(paper: dict) -> dict:
    """
    将 S2 返回的论文对象规整为更稳定的输出结构。
    保留原始字段，同时补扁平的 'doi' / 'arxiv' 便于下游消费。
    """
    if not isinstance(paper, dict):
        return paper
    out = dict(paper)
    ext = paper.get("externalIds") or {}
    out["doi"] = ext.get("DOI") or ""
    out["arxiv"] = ext.get("ArXiv") or ""
    out["corpusId"] = ext.get("CorpusId") or ""
    # authors 规整为名字列表，便于时间线渲染
    authors = paper.get("authors") or []
    if authors and isinstance(authors[0], dict):
        out["authorNames"] = [a.get("name", "") for a in authors]
    else:
        out["authorNames"] = list(authors)
    return out


def get_focal_paper(paper_id: str) -> Optional[dict]:
    """
    获取 focal paper 自身的元数据。

    paper_id 可以是 DOI:xxx / ArXiv:xxx / CorpusId:xxx / 原始 S2 paperId。
    """
    url = f"{S2_BASE}/paper/{paper_id}"
    params = {"fields": FOCAL_FIELDS}
    status, body = _request_with_retry(url, params)
    if status == 200:
        return _normalize_paper(body)
    elif status == 404:
        print(f"[错误] focal paper 不存在: {paper_id} (HTTP 404)", file=sys.stderr)
        return None
    else:
        print(f"[错误] 获取 focal paper 失败: HTTP {status}", file=sys.stderr)
        if isinstance(body, str):
            print(f"        响应体: {body[:300]}", file=sys.stderr)
        return None


def _fetch_related(paper_id: str, endpoint: str, limit: int,
                   nested_key: str) -> list:
    """
    通用分页拉取器，服务于 /citations 与 /references 两个端点。

    参数：
      endpoint   : "citations" 或 "references"
      nested_key : "citingPaper"（前向）或 "citedPaper"（后向）
      limit      : 期望返回条数上限

    返回：list[dict]，每个元素是规整后的嵌套论文对象。
    """
    if limit < 1:
        raise ValueError(f"limit 必须 >= 1，收到 {limit}")
    if limit > HARD_CAP:
        print(f"[警告] limit {limit} 超过硬上限 {HARD_CAP}，已截断。",
              file=sys.stderr)
        limit = HARD_CAP

    aggregated = []
    offset = 0
    next_token = None

    while len(aggregated) < limit:
        page_size = min(PAGE_SIZE, limit - len(aggregated))
        params = {
            "fields": PAPER_FIELDS,
            "limit": page_size,
            "offset": offset,
        }
        if next_token:
            # S2 支持基于 offset 的翻页，也支持 continuation token
            params["offset"] = offset

        url = f"{S2_BASE}/paper/{paper_id}/{endpoint}"
        status, body = _request_with_retry(url, params)

        if status != 200:
            print(f"[错误] S2 /paper/{{id}}/{endpoint} 失败: HTTP {status}。"
                  f"已聚合 {len(aggregated)} 条，停止分页。", file=sys.stderr)
            if isinstance(body, str):
                print(f"        响应体: {body[:300]}", file=sys.stderr)
            break

        data = body.get("data", [])
        for entry in data:
            nested = entry.get(nested_key)
            if nested:
                aggregated.append(_normalize_paper(nested))

        # S2 在结果不足时返回空 data 或长度小于 page_size，表示已到末尾
        if not data or len(data) < page_size:
            break

        offset += page_size
        _rate_limit()

    result = aggregated[:limit]
    return result


def get_citations(paper_id: str, limit: int) -> list:
    """
    前向引用：谁引用了这篇 paper。
    端点 /paper/{id}/citations，嵌套对象为 citingPaper。
    """
    print(f"[前向] 拉取 {paper_id} 的 citations (limit={limit})...",
          file=sys.stderr)
    return _fetch_related(paper_id, "citations", limit, "citingPaper")


def get_references(paper_id: str, limit: int) -> list:
    """
    后向引用：这篇 paper 引用了谁。
    端点 /paper/{id}/references，嵌套对象为 citedPaper。
    """
    print(f"[后向] 拉取 {paper_id} 的 references (limit={limit})...",
          file=sys.stderr)
    return _fetch_related(paper_id, "references", limit, "citedPaper")


def aggregate_by_year(papers: list) -> dict:
    """
    按发表年份（year）聚合论文列表。

    返回结构：
    {
        "total": N,
        "yearRange": [minYear, maxYear],
        "byYear": { "2017": [ {...}, ... ], ... },
        "yearCounts": [ {"year": 2017, "count": 12}, ... ]  # 按年份升序
    }
    year 为 None / 缺失的论文归入 "unknown" 桶。
    """
    by_year = defaultdict(list)
    for p in papers:
        y = p.get("year")
        key = str(y) if y is not None else "unknown"
        by_year[key].append(p)

    years_with_value = [y for y in by_year if y != "unknown"]
    year_range = None
    if years_with_value:
        int_years = sorted(int(y) for y in years_with_value)
        year_range = [int_years[0], int_years[-1]]

    year_counts = [
        {"year": y, "count": len(by_year[y])}
        for y in sorted(by_year.keys(),
                        key=lambda k: (k == "unknown", k))
    ]

    return {
        "total": len(papers),
        "yearRange": year_range,
        "byYear": dict(by_year),
        "yearCounts": year_counts,
    }


def mark_key_turning_points(papers: list,
                            top_k: int = 10,
                            influ_threshold: int = 10) -> list:
    """
    标注"关键转折论文"候选：influentialCitationCount 较高的论文。

    判定规则（取并集）：
      - influentialCitationCount >= influ_threshold，或
      - 在该列表中 influentialCitationCount 排名前 top_k。

    返回：list[dict]，按 influentialCitationCount 降序，每条额外带
    isKeyTurningPoint=True 字段。仅返回被标注为关键转折的论文。
    """
    ranked = sorted(
        papers,
        key=lambda p: (p.get("influentialCitationCount") or 0),
        reverse=True,
    )
    flagged = []
    for i, p in enumerate(ranked):
        influ = p.get("influentialCitationCount") or 0
        is_key = (i < top_k) or (influ >= influ_threshold)
        if is_key:
            p_copy = dict(p)
            p_copy["isKeyTurningPoint"] = True
            p_copy["rankByInfluence"] = i + 1
            flagged.append(p_copy)
    return flagged


def build_citation_graph(paper_id: str,
                         depth: int = 1,
                         limit: int = 500,
                         expand_top: int = DEFAULT_EXPAND_TOP) -> dict:
    """
    构建一篇 focal paper 的引用图谱（前向 + 后向），按年份聚合并标注
    关键转折论文。

    参数：
      paper_id    : focal paper 的 S2 通用 ID（DOI:xxx / ArXiv:xxx / paperId）
      depth       : 展开深度。1 = 仅直接引用；2 = 对 top-K 高引论文再展开一层。
      limit       : 单方向拉取上限。
      expand_top  : depth>=2 时第 2 层展开的 top-K 数量。

    返回 JSON 结构：
    {
        "focalPaper": {...},
        "forwardCitations": {             # 谁引用了这篇
            "total": N,
            "yearRange": [min, max],
            "byYear": {...},
            "yearCounts": [...],
            "keyTurningPoints": [...]
        },
        "backwardReferences": {           # 这篇引用了谁
            "total": N,
            "yearRange": [...],
            "byYear": {...},
            "yearCounts": [...],
            "keyTurningPoints": [...]
        },
        "depth": 1,
        "expandedNodes": [],              # depth>=2 时填充
        "dataSource": "semantic_scholar",
        "degraded": false                 # 限速降级时为 true
    }
    """
    result = {
        "focalPaper": None,
        "forwardCitations": {},
        "backwardReferences": {},
        "depth": depth,
        "expandedNodes": [],
        "dataSource": "semantic_scholar",
        "degraded": False,
    }

    # 0. focal paper 元数据
    focal = get_focal_paper(paper_id)
    if focal is None:
        result["error"] = f"FOCAL_PAPER_NOT_FOUND: {paper_id}"
        return result
    result["focalPaper"] = focal
    focal_s2_id = focal.get("paperId") or paper_id

    # 1. 直接前向 + 后向引用
    citations = get_citations(focal_s2_id, limit)
    references = get_references(focal_s2_id, limit)

    # 限速降级探测：两个方向都为空且非 404，大概率是被限速
    if not citations and not references:
        print("[降级] 前向与后向引用均为空，疑似 S2 限速。建议减少 --depth。",
              file=sys.stderr)
        result["degraded"] = True

    # 2. 按年份聚合 + 标注关键转折
    cit_agg = aggregate_by_year(citations)
    cit_agg["keyTurningPoints"] = mark_key_turning_points(citations)
    result["forwardCitations"] = cit_agg

    ref_agg = aggregate_by_year(references)
    ref_agg["keyTurningPoints"] = mark_key_turning_points(references)
    result["backwardReferences"] = ref_agg

    # 3. 二跳展开（depth >= 2）
    if depth >= 2:
        print(f"[二跳] depth={depth}，对每方向 top-{expand_top} 高引论文再展开一层...",
              file=sys.stderr)
        # 取前向 top-K 与后向 top-K，分别再拉一层
        cit_top = sorted(
            citations,
            key=lambda p: (p.get("citationCount") or 0),
            reverse=True,
        )[:expand_top]
        ref_top = sorted(
            references,
            key=lambda p: (p.get("citationCount") or 0),
            reverse=True,
        )[:expand_top]

        expanded = []
        for p in cit_top + ref_top:
            child_id = p.get("paperId")
            if not child_id:
                continue
            child_cit = get_citations(child_id, limit=100)
            _rate_limit()
            child_ref = get_references(child_id, limit=100)
            _rate_limit()
            expanded.append({
                "sourcePaperId": child_id,
                "sourceTitle": p.get("title", ""),
                "forwardCitationsByYear": aggregate_by_year(child_cit),
                "backwardReferencesByYear": aggregate_by_year(child_ref),
            })
        result["expandedNodes"] = expanded

        # 二跳若大量为空，也标记降级
        empty_children = sum(
            1 for e in expanded
            if not e["forwardCitationsByYear"]["total"]
            and not e["backwardReferencesByYear"]["total"]
        )
        if expanded and empty_children == len(expanded):
            print("[降级] 二跳全部为空，疑似持续限速。建议 --depth 1 重跑。",
                  file=sys.stderr)
            result["degraded"] = True

    return result


# ============ 命令行入口 ============
def main():
    parser = argparse.ArgumentParser(
        description="Semantic Scholar 引用图谱（前向 citations + 后向 references，按年聚合）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("paper_id",
                        help='focal paper 的 S2 通用 ID，如 "DOI:10.xxx" / '
                             '"ArXiv:1706.03762" / <S2 paperId>')
    parser.add_argument("--depth", type=int, default=1,
                        help="引用图展开深度（1=仅直接引用，默认 1；"
                             "2=对 top-K 高引论文再展开一层）")
    parser.add_argument("--limit", type=int, default=500,
                        help=f"单方向拉取上限（1..{HARD_CAP}，默认 500）")
    parser.add_argument("--expand-top", type=int, default=DEFAULT_EXPAND_TOP,
                        help=f"depth>=2 时第 2 层展开的 top-K 高引论文数"
                             f"（默认 {DEFAULT_EXPAND_TOP}）")
    parser.add_argument("--output", "-o", default=None,
                        help="输出 JSON 文件路径（默认打印到 stdout）")
    args = parser.parse_args()

    graph = build_citation_graph(
        paper_id=args.paper_id,
        depth=args.depth,
        limit=args.limit,
        expand_top=args.expand_top,
    )

    payload = json.dumps(graph, ensure_ascii=False, indent=2)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(payload)
        print(f"[输出] 已写入 {args.output}", file=sys.stderr)
    else:
        print(payload)

    # 限速降级时以非零退出码提示上层 skill
    if graph.get("degraded"):
        sys.exit(2)
    if graph.get("error"):
        sys.exit(1)


if __name__ == "__main__":
    main()

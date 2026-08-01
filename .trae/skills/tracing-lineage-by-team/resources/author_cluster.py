#!/usr/bin/env python3
"""
作者团队论文聚合脚本（Semantic Scholar Graph API）
=================================================
功能：
  1. 按名字搜索作者（/author/search）
  2. 获取该作者的论文列表（/author/{id}/papers）
  3. 按年份排序输出，字段含 title / year / venue / citationCount / coauthors

用法：
  python author_cluster.py "Author Name"                  # 默认取首位作者，上限 100
  python author_cluster.py "Author Name" --limit 200       # 指定论文上限
  python author_cluster.py "Author Name" --author-id 12345 # 跳过搜索，直接用已知 S2 authorId
  python author_cluster.py "Author Name" --select 2        # 搜索结果有多个时选第 2 个

输出：JSON（stdout）。结构见 build_output() 的返回。

依赖：requests (pip install requests)
环境变量：S2_API_KEY（可选，有 key 限速更宽松）
"""

import argparse
import json
import os
import sys
import time
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

TIMEOUT = 25

# 作者搜索返回字段
AUTHOR_FIELDS = "authorId,name,affiliations,paperCount,citationCount,hIndex"
# 作者论文返回字段
PAPER_FIELDS = (
    "title,year,venue,externalIds,citationCount,influentialCitationCount,"
    "publicationDate,authors"
)


def _request(url: str, params: Optional[dict] = None, method: str = "GET",
             body: Optional[dict] = None) -> Optional[dict]:
    """
    本地薄封装：GET 走共享 request_with_retry；POST 直接调用（无 retry）。
    返回 JSON 字典或 None — 与原 _request 行为一致。
    """
    if method == "GET":
        status, response_body = _request_with_retry(url, params=params, timeout=TIMEOUT)
        return response_body if status == 200 else None
    else:
        # POST: 共享模块仅支持 GET，POST 走内联
        r = requests.post(url, headers=HEADERS, json=body, params=params, timeout=TIMEOUT)
        _rate_limit()
        if r.status_code == 200:
            return r.json()
        return None
    return None


def search_author(name: str, limit: int = 10) -> list:
    """
    按名字搜索 Semantic Scholar 作者（/author/search）。
    返回候选作者列表，每个含 authorId / name / affiliations / paperCount / citationCount / hIndex。
    """
    # /author/search 需要 URL 编码的 query 参数
    params = {
        "query": name,
        "limit": limit,
        "fields": AUTHOR_FIELDS,
    }
    data = _request(f"{S2_BASE}/author/search", params=params)
    if data is None:
        return []
    total = data.get("total", 0)
    results = data.get("data", [])
    if results:
        print(f"[搜索] 找到 {total} 位匹配作者，返回前 {len(results)} 位。",
              file=sys.stderr)
    else:
        print(f"[搜索] 未找到匹配作者 '{name}'。", file=sys.stderr)
    return results


def get_author_detail(author_id: str) -> Optional[dict]:
    """
    获取单个作者的详情（/author/{id}），作为搜索结果的补充。
    """
    params = {"fields": AUTHOR_FIELDS}
    return _request(f"{S2_BASE}/author/{author_id}", params=params)


def get_author_papers(author_id: str, limit: int = 100) -> list:
    """
    获取作者论文列表（/author/{id}/papers），分页拉取至 limit。
    S2 单页最多 1000 条，这里用 offset 分页。
    """
    papers = []
    offset = 0
    page_size = min(1000, limit)
    while offset < limit:
        this_page = min(page_size, limit - offset)
        params = {
            "fields": PAPER_FIELDS,
            "limit": this_page,
            "offset": offset,
        }
        data = _request(f"{S2_BASE}/author/{author_id}/papers", params=params)
        if data is None:
            break
        page = data.get("data", [])
        if not page:
            break
        papers.extend(page)
        # 如果返回数小于请求页大小，说明没有更多了
        if len(page) < this_page:
            break
        offset += len(page)
    print(f"[论文] 获取到 {len(papers)} 篇论文（authorId={author_id}，上限 {limit}）。",
          file=sys.stderr)
    return papers


def normalize_paper(raw: dict, focal_author_id: str) -> dict:
    """
    将 S2 原始论文记录规范化为输出字段：
    title / year / venue / citationCount / coauthors / paperId / doi / arxivId
    """
    authors = raw.get("authors", []) or []
    coauthors = []
    for a in authors:
        a_id = a.get("authorId")
        a_name = a.get("name", "")
        if a_name:
            coauthors.append({
                "name": a_name,
                "authorId": a_id,
                "isFocal": a_id == focal_author_id if a_id else False,
            })
    external = raw.get("externalIds", {}) or {}
    return {
        "paperId": raw.get("paperId", ""),
        "title": raw.get("title", "") or "",
        "year": raw.get("year"),
        "venue": raw.get("venue", "") or "",
        "citationCount": raw.get("citationCount", 0) or 0,
        "influentialCitationCount": raw.get("influentialCitationCount", 0) or 0,
        "publicationDate": raw.get("publicationDate", ""),
        "doi": external.get("DOI", ""),
        "arxivId": external.get("ArXiv", ""),
        "coauthors": coauthors,
    }


def sort_by_year(papers: list) -> list:
    """
    按年份升序排列；无年份的排到末尾。同年内按引用数降序。
    """
    def sort_key(p):
        y = p.get("year")
        # 无年份用一个大数排到末尾
        year_key = y if y is not None else 99999
        # 同年按引用数降序 → 用负数
        cite_key = -(p.get("citationCount", 0) or 0)
        return (year_key, cite_key)
    return sorted(papers, key=sort_key)


def build_coauthor_stats(papers: list, focal_author_id: str) -> list:
    """
    从论文列表统计合作者频次，返回按合作次数降序的合作者列表。
    用于后续生成合作者网络。
    """
    from collections import Counter, defaultdict
    counter = Counter()
    years = defaultdict(list)
    for p in papers:
        coauths = p.get("coauthors", [])
        for c in coauths:
            cid = c.get("authorId") or c.get("name")
            if cid and cid != focal_author_id:
                counter[c["name"]] += 1
                if p.get("year"):
                    years[c["name"]].append(p["year"])
    stats = []
    for name, count in counter.most_common():
        yr_list = sorted(set(years[name]))
        stats.append({
            "name": name,
            "collaborations": count,
            "years": yr_list,
            "firstYear": yr_list[0] if yr_list else None,
            "lastYear": yr_list[-1] if yr_list else None,
        })
    return stats


def build_output(query: str, author: dict, papers: list, focal_author_id: str) -> dict:
    """
    组装最终 JSON 输出结构。
    """
    sorted_papers = sort_by_year(papers)
    normalized = [normalize_paper(p, focal_author_id) for p in sorted_papers]
    coauthor_stats = build_coauthor_stats(normalized, focal_author_id)
    # 年份范围
    years = [p["year"] for p in normalized if p.get("year") is not None]
    return {
        "query": query,
        "author": {
            "authorId": author.get("authorId", focal_author_id),
            "name": author.get("name", query),
            "affiliations": author.get("affiliations", []),
            "paperCount": author.get("paperCount", len(normalized)),
            "citationCount": author.get("citationCount", 0),
            "hIndex": author.get("hIndex", 0),
        },
        "summary": {
            "totalPapers": len(normalized),
            "yearRange": {
                "start": min(years) if years else None,
                "end": max(years) if years else None,
            },
            "topVenue": _top_venue(normalized),
            "totalCitations": sum(p.get("citationCount", 0) for p in normalized),
        },
        "papers": normalized,
        "coauthorStats": coauthor_stats,
        "dataSource": "semantic_scholar",
        "rateLimited": API_KEY == "",
    }


def _top_venue(papers: list) -> Optional[str]:
    """返回该作者论文出现最多的 venue。"""
    from collections import Counter
    venues = [p.get("venue", "") for p in papers if p.get("venue")]
    if not venues:
        return None
    return Counter(venues).most_common(1)[0][0]


def resolve_author(query: str, author_id: Optional[str] = None,
                   select: int = 0) -> Optional[dict]:
    """
    解析作者：
    - 若提供 author_id，直接用（并取详情）
    - 否则搜索，按 select 索引选择候选
    返回作者 dict（含 authorId / name 等）。
    """
    if author_id:
        detail = get_author_detail(author_id)
        if detail:
            print(f"[作者] 使用已知 authorId={author_id}: {detail.get('name', '?')}",
                  file=sys.stderr)
            return detail
        # 详情取不到，构造最小记录
        return {"authorId": author_id, "name": query}

    candidates = search_author(query)
    if not candidates:
        return None
    if select >= len(candidates):
        print(f"[警告] --select {select} 超出候选数 {len(candidates)}，使用首位。",
              file=sys.stderr)
        select = 0
    chosen = candidates[select]
    print(f"[作者] 选定第 {select + 1} 位: {chosen.get('name', '?')} "
          f"(authorId={chosen.get('authorId')}, papers={chosen.get('paperCount', '?')})",
          file=sys.stderr)
    return chosen


def main():
    parser = argparse.ArgumentParser(
        description="按作者名聚合 Semantic Scholar 论文，按年份排序输出 JSON。"
    )
    parser.add_argument("name", help='作者名，例如 "Geoffrey Hinton"')
    parser.add_argument("--limit", type=int, default=100,
                        help="拉取论文上限（默认 100）")
    parser.add_argument("--author-id", default=None,
                        help="跳过搜索，直接用已知 S2 authorId")
    parser.add_argument("--select", type=int, default=0,
                        help="搜索结果有多个时，选择第 N 个（0 基，默认首位）")
    parser.add_argument("--pretty", action="store_true",
                        help="美化 JSON 输出（默认紧凑）")
    args = parser.parse_args()

    # 解析作者
    author = resolve_author(args.name, author_id=args.author_id,
                            select=args.select)
    if author is None:
        # 搜索失败 → 输出空结构而非崩溃，便于上层降级到本地数据
        print(json.dumps({
            "query": args.name,
            "author": None,
            "summary": {"totalPapers": 0},
            "papers": [],
            "coauthorStats": [],
            "dataSource": "semantic_scholar",
            "rateLimited": API_KEY == "",
            "error": "AUTHOR_NOT_FOUND",
            "msg": f"Semantic Scholar 中未找到作者 '{args.name}'。"
                   "上层 skill 应回退到本地 _index.csv 数据。"
        }, ensure_ascii=False, indent=2 if args.pretty else None))
        sys.exit(1)

    focal_id = author.get("authorId", "")
    # 拉取论文
    raw_papers = get_author_papers(focal_id, limit=args.limit)
    if not raw_papers:
        print(f"[警告] 作者 {author.get('name')} 没有获取到论文。", file=sys.stderr)

    # 组装输出
    output = build_output(args.name, author, raw_papers, focal_id)
    indent = 2 if args.pretty else None
    print(json.dumps(output, ensure_ascii=False, indent=indent))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Semantic Scholar 主题检索脚本（tracing-lineage-by-era 用）
=========================================================
功能：
  调用 Semantic Scholar Graph API 的 /paper/search 端点，按主题关键词
  搜索论文，返回按 citationCount 降序排序的论文列表。支持分页拉取（上限
  1000）、字段选择、年代过滤，以及 429 限速重试。

  该脚本是 tracing-lineage-by-era skill 的 Step 1 数据来源；其结果会与
  本地 _index.csv 合并后进入"分年代脉络"流程。

用法：
  python s2_search.py "attention mechanism" --limit 100
  python s2_search.py "graph neural network" --limit 500 --year 2015-2024
  python s2_search.py "transformer" --limit 1000 --fields "title,year,citationCount,externalIds"
  python s2_search.py "diffusion model" --limit 200 --output results.json

依赖：requests (pip install requests)
环境变量：S2_API_KEY（可选，有 key 限速更宽松：~1 req/s；无 key ~100 req/5min）

输出：JSON 数组（默认打印到 stdout；--output 指定时写入文件）。
     每个元素是 S2 论文对象的一个子集，按 citationCount 降序排列。

注意：
  - S2 /paper/search 端点本身按"相关度"排序，不支持按 citationCount 排序。
    因此本脚本在客户端对聚合后的结果按 citationCount 降序重排，再截断到
    --limit。这意味着拉取规模越大，排序越接近"真实"的引用量序，但耗时
    和请求数也越多（每页 100 条）。
  - 单次请求 limit 上限为 100，超过 100 自动分页。
  - 429 限速时按指数退避重试（1s, 2s, 4s, 8s, 16s），最多 5 次。
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
SEARCH_PATH = "/paper/search"

# 共享客户端：统一 headers / DELAY / retry / Retry-After 头优先
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "_shared"))
from s2_http import API_KEY, HEADERS, DELAY, MAX_RETRIES  # noqa: E402
from s2_http import rate_limit as _rate_limit             # noqa: E402
from s2_http import request_with_retry as _request_with_retry  # noqa: E402

TIMEOUT = 30

# 默认字段：覆盖 tracing-lineage-by-era 所需的全部元数据 + SPECTer v2 嵌入
DEFAULT_FIELDS = (
    "title,authors,year,venue,citationCount,externalIds,"
    "abstract,tldr,embedding.specter_v2"
)

# 单页最大条数（S2 /paper/search 的硬上限）
PAGE_SIZE = 100
# 单次运行允许拉取的绝对上限（与 skill 中"限 1000"对齐）
HARD_CAP = 1000


def search_papers(query: str,
                  limit: int = 100,
                  fields: str = DEFAULT_FIELDS,
                  year: Optional[str] = None) -> list:
    """
    按主题关键词搜索 Semantic Scholar，返回按 citationCount 降序排序的论文列表。

    参数：
      query  : 主题关键词，如 "attention mechanism"
      limit  : 期望返回的论文数上限（1..1000）。实际会分页拉取 ceil(limit/100)
               次请求，客户端按 citationCount 排序后截断到 limit。
      fields : 逗号分隔的字段列表。默认覆盖 tracing-lineage-by-era 全部需求。
      year   : 可选的年代过滤，如 "2015-2024" 或 "2020-"。直接透传给 S2。

    返回：
      list[dict]，每个 dict 是 S2 论文对象的一个子集，按 citationCount 降序。
      失败时返回空列表（并在 stderr 打印诊断信息）。
    """
    if limit < 1:
        raise ValueError(f"limit 必须 >= 1，收到 {limit}")
    if limit > HARD_CAP:
        print(f"[警告] limit {limit} 超过硬上限 {HARD_CAP}，已截断。",
              file=sys.stderr)
        limit = HARD_CAP

    aggregated = []
    offset = 0
    total_reported = None

    while len(aggregated) < limit:
        page_size = min(PAGE_SIZE, limit - len(aggregated))
        params = {
            "query": query,
            "limit": page_size,
            "offset": offset,
            "fields": fields,
        }
        if year:
            params["year"] = year

        status, body = _request_with_retry(
            f"{S2_BASE}{SEARCH_PATH}", params)

        if status != 200:
            print(f"[错误] S2 /paper/search 失败: HTTP {status}。"
                  f"已聚合 {len(aggregated)} 条，停止分页。", file=sys.stderr)
            if isinstance(body, str):
                print(f"        响应体: {body[:300]}", file=sys.stderr)
            break

        data = body.get("data", [])
        total_reported = body.get("total", total_reported)
        aggregated.extend(data)

        # S2 在结果不足时返回空 data 或 data 长度小于 page_size，表示已到末尾
        if not data or len(data) < page_size:
            break
        # 超过 S2 报告的总数也停止
        if total_reported is not None and len(aggregated) >= total_reported:
            break

        offset += page_size
        _rate_limit()

    # 客户端按 citationCount 降序排序（S2 /paper/search 默认按相关度排）
    # citationCount 可能为 None，统一视为 0
    aggregated.sort(
        key=lambda p: (p.get("citationCount") or 0),
        reverse=True,
    )

    # 截断到 limit
    result = aggregated[:limit]

    print(f"[完成] 查询 '{query}': S2 报告 total={total_reported}, "
          f"已聚合 {len(aggregated)} 条, 返回 top {len(result)} "
          f"(按 citationCount 降序).", file=sys.stderr)
    return result


def _normalize_paper(paper: dict) -> dict:
    """
    将 S2 返回的论文对象规整为更稳定的输出结构。
    保留原始字段，同时补一个扁平的 'doi' 便于下游消费。
    """
    if not isinstance(paper, dict):
        return paper
    out = dict(paper)
    ext = paper.get("externalIds") or {}
    out["doi"] = ext.get("DOI") or ""
    out["arxiv"] = ext.get("ArXiv") or ""
    # authors 规整为 list[dict]，保持 S2 原结构
    return out


def main():
    parser = argparse.ArgumentParser(
        description="Semantic Scholar 主题检索（按 citationCount 降序）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("query", help='主题关键词，如 "attention mechanism"')
    parser.add_argument("--limit", type=int, default=100,
                        help=f"返回论文数上限（1..{HARD_CAP}，默认 100）")
    parser.add_argument("--fields", default=DEFAULT_FIELDS,
                        help="逗号分隔的字段列表（默认覆盖 skill 全部需求）")
    parser.add_argument("--year", default=None,
                        help='年代过滤，如 "2015-2024" 或 "2020-"')
    parser.add_argument("--output", "-o", default=None,
                        help="输出 JSON 文件路径（默认打印到 stdout）")
    parser.add_argument("--raw", action="store_true",
                        help="不规整结构，直接输出 S2 原始对象")
    args = parser.parse_args()

    papers = search_papers(
        query=args.query,
        limit=args.limit,
        fields=args.fields,
        year=args.year,
    )

    if not args.raw:
        papers = [_normalize_paper(p) for p in papers]

    payload = json.dumps(papers, ensure_ascii=False, indent=2)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(payload)
        print(f"[输出] 已写入 {args.output}（{len(papers)} 条）",
              file=sys.stderr)
    else:
        print(payload)


if __name__ == "__main__":
    main()

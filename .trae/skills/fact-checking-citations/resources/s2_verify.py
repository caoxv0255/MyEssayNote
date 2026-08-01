#!/usr/bin/env python3
"""
Semantic Scholar 引用反查脚本
=============================
功能：
  1. 按 DOI 或标题搜索论文，核对存在性
  2. 论断核对（claim check）：检查论断是否被 abstract/tldr 支持
  3. "A 引用了 B" 核对（使用 S2 的 references 端点，作为 Crossref 的回退）
  4. 获取论文的 citationCount、influentialCitationCount、embedding

用法：
  python s2_verify.py --doi <doi>                          # 按 DOI 查询
  python s2_verify.py --search "attention is all you need"  # 按标题搜索
  python s2_verify.py --claim-check <paperId> "<claim>"     # 论断核对
  python s2_verify.py --check-reference <paperId_A> <paperId_B>  # A 是否引用了 B
  python s2_verify.py --batch <paperIds.json>               # 批量查询

依赖：requests (pip install requests)
环境变量：S2_API_KEY（可选，有 key 限速更宽松）；S2_DELAY（默认 1.0）覆盖请求间隔
"""

import requests
import os
import json
import sys
import re
from typing import Optional

# ============ 配置 / 共享 HTTP 客户端 ============
S2_BASE = "https://api.semanticscholar.org/graph/v1"

# 共享客户端：统一 headers / DELAY / retry / Retry-After 头优先
sys.path.insert(0, str(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "_shared")))
from s2_http import API_KEY, HEADERS, DELAY, MAX_RETRIES  # noqa: E402
from s2_http import rate_limit as _rate_limit             # noqa: E402
from s2_http import request_with_retry as _request_with_retry  # noqa: E402

TIMEOUT = 20

# 请求字段
PAPER_FIELDS = "title,authors,year,externalIds,abstract,tldr,citationCount,influentialCitationCount,venue,publicationDate"
REFERENCE_FIELDS = "title,authors,year,externalIds,abstract,tldr,citationCount"


def search_by_title(title: str, limit: int = 3) -> list:
    """
    按标题模糊搜索 Semantic Scholar，返回匹配论文列表。
    用于从 AI 给出的标题解析出真实论文。
    """
    params = {
        "query": title,
        "limit": limit,
        "fields": PAPER_FIELDS,
    }
    status, body = _request_with_retry(
        f"{S2_BASE}/paper/search", params=params, timeout=TIMEOUT)
    if status == 200:
        return body.get("data", [])
    print(f"[错误] 搜索失败: HTTP {status}", file=sys.stderr)
    return []


def verify_by_doi(doi: str) -> dict:
    """
    按 DOI 查 Semantic Scholar（使用 DOI: 前缀）。
    """
    doi = doi.strip()
    url = f"{S2_BASE}/paper/DOI:{doi}"
    params = {"fields": PAPER_FIELDS}
    status, body = _request_with_retry(url, params=params, timeout=TIMEOUT)
    if status == 200:
        paper = body
        return {
            "status": "VERIFIED",
            "paperId": paper.get("paperId"),
            "doi": doi,
            "title": paper.get("title", ""),
            "authors": [a.get("name", "") for a in paper.get("authors", [])],
            "year": paper.get("year"),
            "venue": paper.get("venue", ""),
            "citationCount": paper.get("citationCount", 0),
            "influentialCitationCount": paper.get("influentialCitationCount", 0),
            "abstract": paper.get("abstract", ""),
            "tldr": (paper.get("tldr") or {}).get("text", ""),
        }
    elif status == 404:
        return {"status": "NOT_FOUND", "doi": doi, "msg": "DOI 不在 Semantic Scholar 数据库中"}
    else:
        msg = body[:200] if isinstance(body, str) else str(body)[:200]
        return {"status": "ERROR", "doi": doi, "code": status, "msg": msg}


def verify_by_paper_id(paper_id: str) -> dict:
    """
    按 Semantic Scholar paperId 查询。
    paper_id 可以是 S2 paperId、DOI:xxx、ArXiv:xxx、CorpusId:xxx。
    """
    url = f"{S2_BASE}/paper/{paper_id}"
    params = {"fields": PAPER_FIELDS}
    status, body = _request_with_retry(url, params=params, timeout=TIMEOUT)
    if status == 200:
        paper = body
        return {
            "status": "VERIFIED",
            "paperId": paper.get("paperId"),
            "title": paper.get("title", ""),
            "authors": [a.get("name", "") for a in paper.get("authors", [])],
            "year": paper.get("year"),
            "venue": paper.get("venue", ""),
            "citationCount": paper.get("citationCount", 0),
            "influentialCitationCount": paper.get("influentialCitationCount", 0),
            "abstract": paper.get("abstract", ""),
            "tldr": (paper.get("tldr") or {}).get("text", ""),
        }
    elif status == 404:
        return {"status": "NOT_FOUND", "paperId": paper_id}
    else:
        msg = body[:200] if isinstance(body, str) else str(body)[:200]
        return {"status": "ERROR", "paperId": paper_id, "code": status, "msg": msg}


def claim_supported_by_paper(paper_id: str, claim: str) -> dict:
    """
    论断核对：检查 claim 中的关键词是否出现在论文的 abstract 或 tldr 中。

    这是防"论断幻觉"的关键功能——即引用的论文真实存在，
    但 AI 对该论文的论断是编造的。

    注意：这是基于关键词覆盖的检查，不是语义蕴含判断。
    关键词匹配是必要但不充分条件——通过检查不代表论断一定正确，
    但不通过则高度可疑。

    返回：
    {
        "status": "SUPPORTED" | "UNSUPPORTED" | "INCONCLUSIVE",
        "paper_id": "...",
        "claim": "...",
        "matched_keywords": ["keyword1", "keyword2"],
        "unmatched_keywords": ["keyword3"],
        "abstract_available": True/False,
        "tldr_available": True/False,
        "msg": "..."
    }
    """
    # 获取论文的 abstract 和 tldr
    paper = verify_by_paper_id(paper_id)
    if paper.get("status") != "VERIFIED":
        return {
            "status": "INCONCLUSIVE",
            "paper_id": paper_id,
            "claim": claim,
            "msg": f"无法获取论文元数据: {paper.get('msg', '')}"
        }

    abstract = paper.get("abstract", "") or ""
    tldr = paper.get("tldr", "") or ""
    text = (abstract + " " + tldr).lower()

    has_abstract = bool(abstract)
    has_tldr = bool(tldr)

    if not text.strip():
        return {
            "status": "INCONCLUSIVE",
            "paper_id": paper_id,
            "claim": claim,
            "abstract_available": False,
            "tldr_available": False,
            "msg": "论文无 abstract 和 tldr，无法做论断核对"
        }

    # 提取 claim 中的关键词（去除停用词、提取实词）
    stop_words = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "must", "can", "shall", "to", "of", "in",
        "for", "on", "with", "at", "by", "from", "as", "into", "through",
        "during", "before", "after", "above", "below", "up", "down", "out",
        "off", "over", "under", "again", "further", "then", "once", "and",
        "but", "or", "nor", "not", "so", "than", "too", "very", "s", "t",
        "this", "that", "these", "those", "it", "its", "they", "them",
        "their", "we", "our", "you", "your", "he", "she", "his", "her",
        "的", "了", "在", "是", "和", "与", "或", "为", "对", "从", "到",
        "用", "被", "将", "把", "给", "向", "于", "以", "按", "据",
        "论文", "提出", "使用", "方法", "一种", "基于",
    }
    # 英文词 + 中文词混合处理
    words = re.findall(r"[a-zA-Z]{3,}|[\u4e00-\u9fff]{2,}", claim.lower())
    keywords = [w for w in words if w not in stop_words]

    matched = []
    unmatched = []
    for kw in keywords:
        if kw in text:
            matched.append(kw)
        else:
            unmatched.append(kw)

    # 判断标准：>50% 的关键词匹配 → SUPPORTED，否则 UNSUPPORTED
    if not keywords:
        return {
            "status": "INCONCLUSIVE",
            "paper_id": paper_id,
            "claim": claim,
            "msg": "无法从 claim 中提取有效关键词"
        }

    match_ratio = len(matched) / len(keywords)
    if match_ratio >= 0.5:
        status = "SUPPORTED"
        msg = f"✅ {len(matched)}/{len(keywords)} 关键词在 abstract/tldr 中找到（匹配率 {match_ratio:.0%}）"
    else:
        status = "UNSUPPORTED"
        msg = f"❌ 仅 {len(matched)}/{len(keywords)} 关键词在 abstract/tldr 中找到（匹配率 {match_ratio:.0%}），论断可能为幻觉"

    return {
        "status": status,
        "paper_id": paper_id,
        "paper_title": paper.get("title", ""),
        "claim": claim,
        "matched_keywords": matched,
        "unmatched_keywords": unmatched,
        "match_ratio": round(match_ratio, 2),
        "abstract_available": has_abstract,
        "tldr_available": has_tldr,
        "msg": msg
    }


def check_reference_relationship(paper_id_a: str, paper_id_b: str) -> dict:
    """
    核对论文 A 的参考文献中是否包含论文 B。
    使用 S2 的 /paper/{id}/references 端点，作为 Crossref reference 字段的回退。

    paper_id 可以是 S2 paperId、DOI:xxx、ArXiv:xxx。
    """
    url = f"{S2_BASE}/paper/{paper_id_a}/references"
    params = {"fields": REFERENCE_FIELDS, "limit": 500}
    status, body = _request_with_retry(url, params=params, timeout=TIMEOUT)
    if status == 200:
        data = body.get("data", [])
        # 规范化 B 的 ID
        b_id_lower = paper_id_b.lower()
        for ref_entry in data:
            ref_paper = ref_entry.get("citedPaper", {})
            ref_id = (ref_paper.get("paperId") or "").lower()
            ref_doi = (ref_paper.get("externalIds", {}).get("DOI") or "").lower()
            # 多种 ID 匹配
            if (b_id_lower == ref_id or
                b_id_lower == f"doi:{ref_doi}" or
                b_id_lower == ref_doi):
                return {
                    "status": "CONFIRMED",
                    "paper_a": paper_id_a,
                    "paper_b": paper_id_b,
                    "b_title": ref_paper.get("title", ""),
                    "b_year": ref_paper.get("year"),
                    "msg": f"✅ 论文 A 的参考文献中包含论文 B ({ref_paper.get('title', '')[:60]})"
                }
        return {
            "status": "NOT_IN_REFERENCES",
            "paper_a": paper_id_a,
            "paper_b": paper_id_b,
            "a_reference_count": len(data),
            "msg": f"❌ 论文 A 有 {len(data)} 条参考文献，但未找到论文 B"
        }
    elif status == 404:
        return {"status": "ERROR", "msg": f"论文 A 不存在: {paper_id_a}"}
    else:
        msg = body[:200] if isinstance(body, str) else str(body)[:200]
        return {"status": "ERROR", "code": status, "msg": msg}


def batch_verify(paper_ids: list) -> list:
    """
    批量查询论文（使用 S2 /paper/batch 端点，最多 500 个）。
    POST 端点，不走共享 retry（保留 inline）。
    """
    url = f"{S2_BASE}/paper/batch"
    body = {"ids": paper_ids}
    params = {"fields": PAPER_FIELDS}
    try:
        r = requests.post(url, headers=HEADERS, json=body, params=params, timeout=30)
        _rate_limit()
        if r.status_code == 200:
            results = r.json()
            return [
                {
                    "status": "VERIFIED" if p else "NOT_FOUND",
                    "paperId": (p or {}).get("paperId"),
                    "title": (p or {}).get("title", ""),
                    "year": (p or {}).get("year"),
                    "citationCount": (p or {}).get("citationCount", 0),
                }
                for p in results
            ]
        else:
            return [{"status": "ERROR", "code": r.status_code, "msg": r.text[:200]}]
    except Exception as e:
        return [{"status": "ERROR", "msg": str(e)}]


# ============ 命令行入口 ============
def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    if sys.argv[1] == "--doi":
        if len(sys.argv) < 3:
            print("用法: python s2_verify.py --doi <doi>")
            sys.exit(1)
        result = verify_by_doi(sys.argv[2])
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif sys.argv[1] == "--search":
        if len(sys.argv) < 3:
            print("用法: python s2_verify.py --search \"title keywords\"")
            sys.exit(1)
        results = search_by_title(sys.argv[2])
        print(json.dumps(results, ensure_ascii=False, indent=2))

    elif sys.argv[1] == "--claim-check":
        if len(sys.argv) < 4:
            print("用法: python s2_verify.py --claim-check <paperId> \"<claim text>\"")
            sys.exit(1)
        result = claim_supported_by_paper(sys.argv[2], sys.argv[3])
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif sys.argv[1] == "--check-reference":
        if len(sys.argv) < 4:
            print("用法: python s2_verify.py --check-reference <paperId_A> <paperId_B>")
            sys.exit(1)
        result = check_reference_relationship(sys.argv[2], sys.argv[3])
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif sys.argv[1] == "--batch":
        if len(sys.argv) < 3:
            print("用法: python s2_verify.py --batch <paperIds.json>")
            sys.exit(1)
        with open(sys.argv[2], "r", encoding="utf-8") as f:
            ids = json.load(f)
        results = batch_verify(ids)
        print(json.dumps(results, ensure_ascii=False, indent=2))

    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()

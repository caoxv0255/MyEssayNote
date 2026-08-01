#!/usr/bin/env python3
"""
Crossref 引用反查脚本
====================
功能：
  1. 按 DOI 查 Crossref，核对 title/author/year
  2. 提取 reference 字段，核对 "A 是否真的引用了 B"
  3. 批量核对多个 DOI

用法：
  python crossref_verify.py <doi>                          # 单个 DOI 查询
  python crossref_verify.py --check-reference <doi_A> <doi_B>  # 核对 A 是否引用了 B
  python crossref_verify.py --batch <doi_list.json>         # 批量查询

依赖：requests (pip install requests)
"""

import requests
import time
import json
import sys
import os
from typing import Optional

# ============ 配置 ============
CROSSREF_BASE = "https://api.crossref.org/works"
# 填入你的邮箱以进入 Crossref polite pool（更快、更稳定）
MAILTO = os.environ.get("CROSSREF_MAILTO", "researcher@example.com")
HEADERS = {
    "User-Agent": f"AcademicPKM/1.0 (mailto:{MAILTO})",
    "Accept": "application/json",
}
DELAY = float(os.environ.get("CROSSREF_DELAY", "1.1"))  # polite pool 建议间隔 >= 1 秒
TIMEOUT = 20


def verify_by_doi(doi: str) -> dict:
    """
    按 DOI 查 Crossref，返回核对结果。

    返回结构：
    {
        "status": "VERIFIED" | "NOT_FOUND" | "ERROR",
        "doi": "...",
        "title": "...",
        "authors": ["Family1", "Family2", ...],
        "year": 2017,
        "venue": "...",
        "references": [{"doi": "...", "title": "..."}, ...],  # 出版商登记的参考文献
        "is_referenced_by_count": 12345,
        "reference_count": 50
    }
    """
    doi = doi.strip().lower()
    url = f"{CROSSREF_BASE}/{doi}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code == 200:
            msg = r.json()["message"]
            # 提取标题（Crossref 返回列表，取第一个）
            title = msg.get("title", [""])[0] if msg.get("title") else ""
            # 提取作者
            authors = [a.get("family", "") for a in msg.get("author", [])]
            # 提取年份
            year = None
            date_parts = msg.get("published", {}).get("date-parts", [[None]])
            if date_parts and date_parts[0]:
                year = date_parts[0][0]
            # 提取参考文献列表（关键：用于 "A 引用了 B" 核对）
            references = []
            for ref in msg.get("reference", []):
                references.append({
                    "doi": ref.get("DOI", "").lower() if ref.get("DOI") else None,
                    "title": ref.get("article-title", "") or ref.get("unstructured", ""),
                    "year": ref.get("year"),
                })
            return {
                "status": "VERIFIED",
                "doi": doi,
                "title": title,
                "authors": authors,
                "year": year,
                "venue": msg.get("container-title", [""])[0] if msg.get("container-title") else "",
                "references": references,
                "reference_count": msg.get("reference-count", 0),
                "is_referenced_by_count": msg.get("is-referenced-by-count", 0),
            }
        elif r.status_code == 404:
            return {"status": "NOT_FOUND", "doi": doi, "msg": "DOI 不存在于 Crossref 数据库"}
        else:
            return {"status": "ERROR", "doi": doi, "code": r.status_code, "msg": r.text[:200]}
    except requests.exceptions.Timeout:
        return {"status": "ERROR", "doi": doi, "msg": "请求超时"}
    except Exception as e:
        return {"status": "ERROR", "doi": doi, "msg": str(e)}


def verify_claim_in_references(doi_a: str, doi_b: str) -> dict:
    """
    核对论文 A 是否真的在参考文献中引用了论文 B。

    这是防 "A 引用了 B" 幻觉的关键功能。
    使用 Crossref 的 reference 字段（出版商登记的参考文献列表）。

    返回：
    {
        "status": "CONFIRMED" | "NOT_IN_REFERENCES" | "A_HAS_NO_REFERENCES" | "ERROR",
        "doi_a": "...",
        "doi_b": "...",
        "a_title": "...",
        "a_reference_count": 50,
        "msg": "..."
    }
    """
    doi_a = doi_a.strip().lower()
    doi_b = doi_b.strip().lower()

    # 查论文 A 的元数据
    meta_a = verify_by_doi(doi_a)
    time.sleep(DELAY)

    if meta_a.get("status") != "VERIFIED":
        return {
            "status": "ERROR",
            "doi_a": doi_a,
            "doi_b": doi_b,
            "msg": f"无法获取论文 A 的元数据: {meta_a.get('msg', '')}"
        }

    references = meta_a.get("references", [])
    if not references:
        return {
            "status": "A_HAS_NO_REFERENCES",
            "doi_a": doi_a,
            "doi_b": doi_b,
            "a_title": meta_a["title"],
            "a_reference_count": 0,
            "msg": "论文 A 在 Crossref 中没有登记参考文献列表（部分出版商未登记），建议用 Semantic Scholar 回退核对"
        }

    # 在 A 的参考文献中搜索 B 的 DOI
    for ref in references:
        if ref.get("doi") and ref["doi"] == doi_b:
            return {
                "status": "CONFIRMED",
                "doi_a": doi_a,
                "doi_b": doi_b,
                "a_title": meta_a["title"],
                "b_title_in_refs": ref.get("title", ""),
                "a_reference_count": meta_a["reference_count"],
                "msg": f"✅ 论文 A ({meta_a['title'][:60]}...) 的参考文献中包含论文 B (DOI: {doi_b})"
            }

    return {
        "status": "NOT_IN_REFERENCES",
        "doi_a": doi_a,
        "doi_b": doi_b,
        "a_title": meta_a["title"],
        "a_reference_count": meta_a["reference_count"],
        "msg": f"❌ 论文 A 有 {meta_a['reference_count']} 条参考文献，但未找到 DOI 为 {doi_b} 的论文 B。可能是 B 未被 A 引用，或 Crossref 参考文献列表不完整。"
    }


def batch_verify(doi_list: list) -> list:
    """批量核对 DOI 列表，返回结果列表。"""
    results = []
    for i, doi in enumerate(doi_list):
        print(f"[{i+1}/{len(doi_list)}] 正在核对: {doi}", file=sys.stderr)
        result = verify_by_doi(doi)
        results.append(result)
        if i < len(doi_list) - 1:
            time.sleep(DELAY)
    return results


def fuzzy_title_match(title_a: str, title_b: str, threshold: float = 0.8) -> bool:
    """
    简单的标题模糊匹配（基于词集 Jaccard 相似度）。
    用于核对 AI 给出的标题与 Crossref 返回的标题是否一致。
    """
    if not title_a or not title_b:
        return False
    words_a = set(title_a.lower().split())
    words_b = set(title_b.lower().split())
    if not words_a or not words_b:
        return False
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union) >= threshold


def verify_citation_entry(citation: dict) -> dict:
    """
    核对单个引用条目（含 DOI + 可选的标题/作者/年份用于交叉验证）。

    输入：
    {
        "doi": "10.xxx/yyy",       # 必需
        "title": "Paper Title",    # 可选，用于交叉验证
        "authors": ["Smith"],      # 可选
        "year": 2017,              # 可选
        "claim": "proposed XXX"    # 可选，论断文本（Crossref 不做论断核对，由 s2_verify.py 负责）
    }

    返回核对结果。
    """
    doi = citation.get("doi", "").strip()
    if not doi:
        return {"status": "ERROR", "msg": "缺少 DOI", "citation": citation}

    result = verify_by_doi(doi)
    time.sleep(DELAY)

    if result["status"] != "VERIFIED":
        return result

    # 交叉验证标题
    if citation.get("title"):
        if not fuzzy_title_match(citation["title"], result["title"]):
            result["title_match"] = "MISMATCH"
            result["title_expected"] = citation["title"]
            result["title_actual"] = result["title"]
        else:
            result["title_match"] = "OK"

    # 交叉验证年份
    if citation.get("year"):
        if result.get("year") and abs(result["year"] - citation["year"]) > 1:
            result["year_match"] = "MISMATCH"
            result["year_expected"] = citation["year"]
            result["year_actual"] = result["year"]
        else:
            result["year_match"] = "OK"

    return result


# ============ 命令行入口 ============
def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    if sys.argv[1] == "--check-reference":
        if len(sys.argv) < 4:
            print("用法: python crossref_verify.py --check-reference <doi_A> <doi_B>")
            sys.exit(1)
        result = verify_claim_in_references(sys.argv[2], sys.argv[3])
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif sys.argv[1] == "--batch":
        if len(sys.argv) < 3:
            print("用法: python crossref_verify.py --batch <doi_list.json>")
            sys.exit(1)
        with open(sys.argv[2], "r", encoding="utf-8") as f:
            doi_list = json.load(f)
        results = batch_verify(doi_list)
        print(json.dumps(results, ensure_ascii=False, indent=2))

    else:
        # 单个 DOI 查询
        doi = sys.argv[1]
        result = verify_by_doi(doi)
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

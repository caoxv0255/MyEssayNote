#!/usr/bin/env python3
"""
CCF-A 论文自动化爬取与分类存储系统
=====================================

三阶段流水线（按 README.md 描述的接口）：

  Stage 1  DBLP 爬取全量论文清单（87 venue × N 年）  ->  _index.csv
  Stage 2  OpenAlex 批量富化引用数 + 摘要              ->  _abstracts.jsonl
  Stage 3  筛高分论文 + arXiv 下载 PDF + 分层目录     ->  _high_impact.csv + AI/.../*.pdf

命令行：
    python ccf_crawler.py stage1 --years 2023-2025
    python ccf_crawler.py stage2
    python ccf_crawler.py stage3
    python ccf_crawler.py all     --years 2023-2025
    python ccf_crawler.py report

依赖：requests（pip install requests）
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import random
import re
import sys
import time
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Optional

try:
    import requests
except ImportError:
    sys.stderr.write("[错误] 缺少 requests，请先执行: pip install requests\n")
    sys.exit(1)


# ============================================================
# 配置（与 README.md 表格保持一致）
# ============================================================
DEFAULT_YEAR_START = 2023
DEFAULT_YEAR_END = 2025
DBLP_DELAY = 8.0        # 请求间隔（秒）
ARXIV_DELAY = 3.5       # arXiv 请求间隔（秒）
HIGH_MIN_CIT = 30       # 高影响力论文引用阈值
HIGH_TOPN = 12          # 每个 venue×year 取 top N
PDF_CAP = 1500          # PDF 下载总数上限
MAX_PAGES_PER_VY = 20   # 每 venue×year 最多拉 20 页（每页 100 -> 2000 篇）
PAGE_SIZE = 100

# ============================================================
# 87 个 CCF-A venue（含 area / area_folder / stream 路径）
# （从 _venue_report.txt 反推整理，匹配 DBLP streams 命名）
# ============================================================
VENUES: list[dict] = [
    # ---------- 人工智能（17） ----------
    {"name": "AAAI",       "area": "ai",          "area_folder": "AI",            "kind": "conf",    "stream": "streams/conf/aaai"},
    {"name": "IJCAI",      "area": "ai",          "area_folder": "AI",            "kind": "conf",    "stream": "streams/conf/ijcai"},
    {"name": "ICML",       "area": "ai",          "area_folder": "AI",            "kind": "conf",    "stream": "streams/conf/icml"},
    {"name": "NeurIPS",    "area": "ai",          "area_folder": "AI",            "kind": "conf",    "stream": "streams/conf/nips"},
    {"name": "ICLR",       "area": "ai",          "area_folder": "AI",            "kind": "conf",    "stream": "streams/conf/iclr"},
    {"name": "ACL",        "area": "ai",          "area_folder": "AI",            "kind": "conf",    "stream": "streams/conf/acl"},
    {"name": "EMNLP",      "area": "ai",          "area_folder": "AI",            "kind": "conf",    "stream": "streams/conf/emnlp"},
    {"name": "CVPR",       "area": "ai",          "area_folder": "AI",            "kind": "conf",    "stream": "streams/conf/cvpr"},
    {"name": "ICCV",       "area": "ai",          "area_folder": "AI",            "kind": "conf",    "stream": "streams/conf/iccv"},
    {"name": "ECCV",       "area": "ai",          "area_folder": "AI",            "kind": "conf",    "stream": "streams/conf/eccv"},
    {"name": "KR",         "area": "ai",          "area_folder": "AI",            "kind": "conf",    "stream": "streams/conf/kr"},
    {"name": "AAMAS",      "area": "ai",          "area_folder": "AI",            "kind": "conf",    "stream": "streams/conf/amas"},
    {"name": "COLT",       "area": "ai",          "area_folder": "AI",            "kind": "conf",    "stream": "streams/conf/colt"},
    {"name": "TPAMI",      "area": "ai",          "area_folder": "AI",            "kind": "journal", "stream": "streams/journals/pami"},
    {"name": "IJCV",       "area": "ai",          "area_folder": "AI",            "kind": "journal", "stream": "streams/journals/ijcv"},
    {"name": "JMLR",       "area": "ai",          "area_folder": "AI",            "kind": "journal", "stream": "streams/journals/jmlr"},
    {"name": "AIJ",        "area": "ai",          "area_folder": "AI",            "kind": "journal", "stream": "streams/journals/aij"},
    # ---------- 数据库/数据挖掘/内容检索（10） ----------
    {"name": "SIGMOD",     "area": "database",    "area_folder": "Database",      "kind": "conf",    "stream": "streams/conf/sigmod"},
    {"name": "VLDB",       "area": "database",    "area_folder": "Database",      "kind": "conf",    "stream": "streams/conf/vldb"},
    {"name": "ICDE",       "area": "database",    "area_folder": "Database",      "kind": "conf",    "stream": "streams/conf/icde"},
    {"name": "KDD",        "area": "database",    "area_folder": "Database",      "kind": "conf",    "stream": "streams/conf/kdd"},
    {"name": "SIGIR",      "area": "database",    "area_folder": "Database",      "kind": "conf",    "stream": "streams/conf/sigir"},
    {"name": "WWW",        "area": "database",    "area_folder": "Database",      "kind": "conf",    "stream": "streams/conf/www"},
    {"name": "TKDE",       "area": "database",    "area_folder": "Database",      "kind": "journal", "stream": "streams/journals/tkde"},
    {"name": "TOIS",       "area": "database",    "area_folder": "Database",      "kind": "journal", "stream": "streams/journals/tois"},
    {"name": "TODS",       "area": "database",    "area_folder": "Database",      "kind": "journal", "stream": "streams/journals/tods"},
    {"name": "VLDBJ",      "area": "database",    "area_folder": "Database",      "kind": "journal", "stream": "streams/journals/vldb"},
    # ---------- 计算机网络（6） ----------
    {"name": "SIGCOMM",    "area": "networks",    "area_folder": "Networks",      "kind": "conf",    "stream": "streams/conf/sigcomm"},
    {"name": "NSDI",       "area": "networks",    "area_folder": "Networks",      "kind": "conf",    "stream": "streams/conf/nsdi"},
    {"name": "INFOCOM",    "area": "networks",    "area_folder": "Networks",      "kind": "conf",    "stream": "streams/conf/infocom"},
    {"name": "CoNEXT",     "area": "networks",    "area_folder": "Networks",      "kind": "conf",    "stream": "streams/conf/conext"},
    {"name": "TON",        "area": "networks",    "area_folder": "Networks",      "kind": "journal", "stream": "streams/journals/ton"},
    {"name": "JSAC",       "area": "networks",    "area_folder": "Networks",      "kind": "journal", "stream": "streams/journals/jsac"},
    # ---------- 网络与信息安全（9） ----------
    {"name": "S&P",        "area": "security",    "area_folder": "Security",      "kind": "conf",    "stream": "streams/conf/sp"},
    {"name": "CCS",        "area": "security",    "area_folder": "Security",      "kind": "conf",    "stream": "streams/conf/ccs"},
    {"name": "USENIXSec",  "area": "security",    "area_folder": "Security",      "kind": "conf",    "stream": "streams/conf/uss"},
    {"name": "NDSS",       "area": "security",    "area_folder": "Security",      "kind": "conf",    "stream": "streams/conf/ndss"},
    {"name": "CRYPTO",     "area": "security",    "area_folder": "Security",      "kind": "conf",    "stream": "streams/conf/crypto"},
    {"name": "EUROCRYPT",  "area": "security",    "area_folder": "Security",      "kind": "conf",    "stream": "streams/conf/eurocrypt"},
    {"name": "TIFS",       "area": "security",    "area_folder": "Security",      "kind": "journal", "stream": "streams/journals/tifs"},
    {"name": "TDSC",       "area": "security",    "area_folder": "Security",      "kind": "journal", "stream": "streams/journals/tdsc"},
    {"name": "JCS",        "area": "security",    "area_folder": "Security",      "kind": "journal", "stream": "streams/journals/jcs"},
    # ---------- 软件工程/程序设计（10） ----------
    {"name": "ICSE",       "area": "software",    "area_folder": "Software",      "kind": "conf",    "stream": "streams/conf/icse"},
    {"name": "FSE",        "area": "software",    "area_folder": "Software",      "kind": "conf",    "stream": "streams/conf/sigsoft"},
    {"name": "ASE",        "area": "software",    "area_folder": "Software",      "kind": "conf",    "stream": "streams/conf/ase"},
    {"name": "ISSTA",      "area": "software",    "area_folder": "Software",      "kind": "conf",    "stream": "streams/conf/issta"},
    {"name": "POPL",       "area": "software",    "area_folder": "Software",      "kind": "conf",    "stream": "streams/conf/popl"},
    {"name": "PLDI",       "area": "software",    "area_folder": "Software",      "kind": "conf",    "stream": "streams/conf/pldi"},
    {"name": "OOPSLA",     "area": "software",    "area_folder": "Software",      "kind": "conf",    "stream": "streams/conf/oopsla"},
    {"name": "TOSEM",      "area": "software",    "area_folder": "Software",      "kind": "journal", "stream": "streams/journals/tosem"},
    {"name": "TSE",        "area": "software",    "area_folder": "Software",      "kind": "journal", "stream": "streams/journals/tse"},
    {"name": "TOPS",       "area": "software",    "area_folder": "Software",      "kind": "journal", "stream": "streams/journals/toplas"},
    # ---------- 计算机科学理论（7） ----------
    {"name": "STOC",       "area": "theory",      "area_folder": "Theory",        "kind": "conf",    "stream": "streams/conf/stoc"},
    {"name": "FOCS",       "area": "theory",      "area_folder": "Theory",        "kind": "conf",    "stream": "streams/conf/focs"},
    {"name": "SODA",       "area": "theory",      "area_folder": "Theory",        "kind": "conf",    "stream": "streams/conf/soda"},
    {"name": "LICS",       "area": "theory",      "area_folder": "Theory",        "kind": "conf",    "stream": "streams/conf/lics"},
    {"name": "JACM",       "area": "theory",      "area_folder": "Theory",        "kind": "journal", "stream": "streams/journals/jacm"},
    {"name": "TOCT",       "area": "theory",      "area_folder": "Theory",        "kind": "journal", "stream": "streams/journals/toct"},
    {"name": "SICOMP",     "area": "theory",      "area_folder": "Theory",        "kind": "journal", "stream": "streams/journals/siamcomp"},
    # ---------- 计算机图形学（4） ----------
    {"name": "SIGGRAPH",   "area": "graphics",    "area_folder": "Graphics",      "kind": "conf",    "stream": "streams/conf/siggraph"},
    {"name": "CHI",        "area": "graphics",    "area_folder": "Graphics",      "kind": "conf",    "stream": "streams/conf/chi"},
    {"name": "TOG",        "area": "graphics",    "area_folder": "Graphics",      "kind": "journal", "stream": "streams/journals/tog"},
    {"name": "TVCG",       "area": "graphics",    "area_folder": "Graphics",      "kind": "journal", "stream": "streams/journals/tvcg"},
    # ---------- 人机交互（4） ----------
    {"name": "UIST",       "area": "hci",         "area_folder": "HCI",           "kind": "conf",    "stream": "streams/conf/uist"},
    {"name": "CSCW",       "area": "hci",         "area_folder": "HCI",           "kind": "conf",    "stream": "streams/conf/cscw"},
    {"name": "IUI",        "area": "hci",         "area_folder": "HCI",           "kind": "conf",    "stream": "streams/conf/iui"},
    {"name": "IMWUT",      "area": "hci",         "area_folder": "HCI",           "kind": "journal", "stream": "streams/journals/imwut"},
    # ---------- 体系结构/并行与分布/存储（12） ----------
    {"name": "ISCA",       "area": "architecture","area_folder": "Architecture",  "kind": "conf",    "stream": "streams/conf/isca"},
    {"name": "MICRO",      "area": "architecture","area_folder": "Architecture",  "kind": "conf",    "stream": "streams/conf/micro"},
    {"name": "HPCA",       "area": "architecture","area_folder": "Architecture",  "kind": "conf",    "stream": "streams/conf/hpca"},
    {"name": "ASPLOS",     "area": "architecture","area_folder": "Architecture",  "kind": "conf",    "stream": "streams/conf/asplos"},
    {"name": "SC",         "area": "architecture","area_folder": "Architecture",  "kind": "conf",    "stream": "streams/conf/sc"},
    {"name": "PPoPP",      "area": "architecture","area_folder": "Architecture",  "kind": "conf",    "stream": "streams/conf/ppopp"},
    {"name": "DAC",        "area": "architecture","area_folder": "Architecture",  "kind": "conf",    "stream": "streams/conf/dac"},
    {"name": "USENIX ATC", "area": "architecture","area_folder": "Architecture",  "kind": "conf",    "stream": "streams/conf/atc"},
    {"name": "FAST",       "area": "architecture","area_folder": "Architecture",  "kind": "conf",    "stream": "streams/conf/fast"},
    {"name": "TOCS",       "area": "architecture","area_folder": "Architecture",  "kind": "journal", "stream": "streams/journals/tocs"},
    {"name": "TACO",       "area": "architecture","area_folder": "Architecture",  "kind": "journal", "stream": "streams/journals/taco"},
    {"name": "IEEE TC",    "area": "architecture","area_folder": "Architecture",  "kind": "journal", "stream": "streams/journals/tc"},
    # ---------- 交叉/综合/新兴（8） ----------
    {"name": "ICDM",       "area": "inter",       "area_folder": "Interdisciplinary","kind": "conf",  "stream": "streams/conf/icdm"},
    {"name": "CIKM",       "area": "inter",       "area_folder": "Interdisciplinary","kind": "conf",  "stream": "streams/conf/cikm"},
    {"name": "WSDM",       "area": "inter",       "area_folder": "Interdisciplinary","kind": "conf",  "stream": "streams/conf/wsdm"},
    {"name": "RecSys",     "area": "inter",       "area_folder": "Interdisciplinary","kind": "conf",  "stream": "streams/conf/recsys"},
    {"name": "ICRA",       "area": "inter",       "area_folder": "Interdisciplinary","kind": "conf",  "stream": "streams/conf/icra"},
    {"name": "IROS",       "area": "inter",       "area_folder": "Interdisciplinary","kind": "conf",  "stream": "streams/conf/iros"},
    {"name": "TPDS",       "area": "inter",       "area_folder": "Interdisciplinary","kind": "journal","stream": "streams/journals/tpds"},
    {"name": "TIST",       "area": "inter",       "area_folder": "Interdisciplinary","kind": "journal","stream": "streams/journals/tist"},
]

VENUES_BY_NAME = {v["name"]: v for v in VENUES}
assert len(VENUES) == 87, f"VENUES 应为 87 个, 实际 {len(VENUES)}"


# ============================================================
# 通用工具
# ============================================================
DBLP_BASE = "https://dblp.org/db"
DBLP_SEARCH = "https://dblp.org/search/publ/api"
OPENALEX_BASE = "https://api.openalex.org/works"
ARXIV_API = "http://export.arxiv.org/api/query"

ROOT = Path(__file__).resolve().parent
STATE_DIR = ROOT / "state"
DBLP_CACHE = STATE_DIR / "dblp_cache"
STATE_DIR.mkdir(exist_ok=True)
DBLP_CACHE.mkdir(exist_ok=True)

LOG_PATH = ROOT / "_crawl_log.txt"


def log(msg: str) -> None:
    """追加一行到运行日志（与原 _crawl_log.txt 兼容）。"""
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, file=sys.stderr)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


# ============================================================
# 带退避的请求（熔断器：429 / 连接错误）
# ============================================================
def _request_with_backoff(
    url: str,
    *,
    base_delay: float,
    max_retries: int = 3,
    timeout: float = 30.0,
    params: Optional[dict] = None,
    headers: Optional[dict] = None,
) -> Optional[requests.Response]:
    """
    带指数退避的 GET 请求。连续 max_retries 次失败后返回 None。

    退避策略（与 README 描述一致）：
      - 429：等待 30s 后重试，最多 max_retries 次
      - 连接错误：等待 30s 后重试
      - 熔断器：连续 3 次失败 -> 暂停 600s（仅在同一函数调用内递增）
    """
    consecutive_failures = 0
    backoff = 30.0
    for attempt in range(max_retries):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=timeout)
            if r.status_code == 200:
                return r
            if r.status_code == 429:
                log(f"429 限速, 等待 {backoff:.1f}s")
                time.sleep(backoff)
                consecutive_failures += 1
            else:
                log(f"HTTP {r.status_code}: {url}")
                time.sleep(base_delay)
                consecutive_failures += 1
        except requests.exceptions.RequestException as e:
            log(f"连接错误 ({e!r}), 等待 {backoff:.1f}s")
            time.sleep(backoff)
            consecutive_failures += 1

        if consecutive_failures >= 3:
            log(f"熔断: 连续 {consecutive_failures} 次失败, 暂停 600s")
            time.sleep(600)
            consecutive_failures = 0
    return None


# ============================================================
# Stage 1: DBLP 爬取全量论文清单
# ============================================================
def _dblp_xml_for_venue_year(stream_path: str, year: int, page: int) -> Optional[str]:
    """
    DBLP 拉取：优先用 stream 路径的逐年 XML（最稳定），失败时返回 None。

    实际观察：DBLP 的 `streams/conf/<x>/<year>.xml` 端点常返回 404（路径已变）；
    stage1 内部用 _dblp_search_paginated 回退到搜索 API。
    本函数仅作 stream 端点快速探测，存在即返回。
    """
    candidates = [
        f"{DBLP_BASE}/{stream_path}/{year}.xml",
    ]
    for url in candidates:
        r = _request_with_backoff(url, base_delay=DBLP_DELAY, max_retries=2)
        if r is not None and r.status_code == 200:
            return r.text
        time.sleep(DBLP_DELAY)
    return None


def _dblp_search_paginated(venue_name: str, year: int, page_size: int = 100) -> list[dict]:
    """
    用 DBLP 搜索 API 按 venue 名称 + year 拉取论文。

    URL: https://dblp.org/search/publ/api?q=venue:<Venue>+year:<YYYY>&format=json&h=100&f=<offset>

    返回：list[hit dict]，每个含 key / info / venue / year / title / authors / ee / doi。
    """
    out: list[dict] = []
    offset = 0
    # 一次最多 5 页，避免触发 DBLP 限速
    for page_idx in range(5):
        params = {
            "q": f"venue:{venue_name} year:{year}",
            "format": "json",
            "h": page_size,
            "f": offset,
        }
        r = _request_with_backoff(DBLP_SEARCH, base_delay=DBLP_DELAY, max_retries=2,
                                   params=params)
        if r is None or r.status_code != 200:
            break
        try:
            data = r.json()
        except Exception:
            break
        hits = (data.get("result") or {}).get("hits") or {}
        hit_list = hits.get("hit") or []
        if not hit_list:
            break
        out.extend(hit_list)
        total = hits.get("@total", "0")
        try:
            total_n = int(total)
        except ValueError:
            total_n = 0
        if len(out) >= total_n or len(hit_list) < page_size:
            break
        offset += page_size
        time.sleep(DBLP_DELAY)
    return out


def _dblp_hit_to_row(hit: dict, venue: dict, year: int) -> Optional[dict]:
    """从 DBLP JSON hit 转为 _index.csv 行。"""
    info = hit.get("info") or {}
    title = (info.get("title") or "").strip()
    if not title:
        return None
    # authors: list[dict{text: "..."}]，转;分隔
    authors_field = info.get("authors") or {}
    author_list = authors_field.get("author") or []
    if isinstance(author_list, dict):
        author_list = [author_list]
    authors = "; ".join(
        re.sub(r"\s+", " ", a.get("text", "")).strip()
        for a in author_list if isinstance(a, dict)
    )
    # venue / year: hit 顶层有 year；venue 从 info.venue 取（可能为 str 或 dict）
    y = int(info.get("year", year) or year)
    if y != year:
        return None
    venue_field = info.get("venue")
    if isinstance(venue_field, str):
        venue_full = venue_field
    elif isinstance(venue_field, dict):
        venue_full = venue_field.get("text", venue["name"])
    else:
        venue_full = venue["name"]
    # ee / doi
    ee = info.get("ee") or ""
    doi = ""
    ee_str = ""
    if isinstance(ee, str):
        ee_str = ee
        m = re.search(r"doi\.org/(10\.[^<\s]+)", ee)
        if m:
            doi = m.group(1)
    elif isinstance(ee, list):
        for u in ee:
            u = str(u)
            if not ee_str:
                ee_str = u
            m = re.search(r"doi\.org/(10\.[^<\s]+)", u)
            if m and not doi:
                doi = m.group(1)
    # arXiv 推断
    arxiv_id = ""
    for u in (ee_str if isinstance(ee_str, list) else [ee_str]):
        if "arxiv.org/abs/" in str(u):
            m = re.search(r"arxiv\.org/abs/([\w./\-]+)", str(u))
            if m:
                arxiv_id = m.group(1)
                break
    return {
        "id": info.get("key", hit.get("id", "")),
        "title": re.sub(r"\s+", " ", title),
        "authors": authors,
        "year": year,
        "venue": venue["name"],
        "kind": venue["kind"],
        "area": venue["area"],
        "area_folder": venue["area_folder"],
        "stream": venue["stream"],
        "type": "Conference and Workshop Papers" if venue["kind"] == "conf" else "Journal Articles",
        "doi": doi,
        "ee": ee_str if isinstance(ee_str, str) else (ee_str[0] if ee_str else ""),
        "arxiv_id": arxiv_id,
        "citation_count": 0,
        "tldr": "",
        "local_pdf": "",
    }


_DBLP_HIT_RE = re.compile(r'<hit[^>]*id="([^"]+)"', re.DOTALL)
_DBLP_INFO_RE = re.compile(
    r'<info\s+(?:key="([^"]+)"\s+)?(?:mdate="[^"]*"\s+)?>(.*?)</info>',
    re.DOTALL,
)
_DBLP_TITLE_RE = re.compile(r"<title>(.*?)</title>", re.DOTALL)
_DBLP_YEAR_RE = re.compile(r"<year>(\d{4})</year>")
_DBLP_AUTHORS_RE = re.compile(r"<author>(.*?)</author>", re.DOTALL)
_DBLP_DOI_RE = re.compile(r"<ee[^>]*>https?://doi\.org/(10\.[^<\s]+)</ee>")
_DBLP_EE_RE = re.compile(r"<ee[^>]*>(https?://[^<\s]+)</ee>")


def _parse_dblp_xml(xml_text: str, venue: dict, year: int) -> list[dict]:
    """从 DBLP XML 中解析论文记录。"""
    rows: list[dict] = []
    for hit in _DBLP_HIT_RE.finditer(xml_text):
        hit_id = hit.group(1)
        info = _DBLP_INFO_RE.search(hit.group(0))
        if not info:
            continue
        block = info.group(2)
        # 推断 year：优先用 block 内的 <year>，否则用入参
        y_match = _DBLP_YEAR_RE.search(block)
        y = int(y_match.group(1)) if y_match else year
        if y != year:
            continue
        title_match = _DBLP_TITLE_RE.search(block)
        title = (title_match.group(1) if title_match else "").strip()
        title = re.sub(r"\s+", " ", title)
        authors = [
            re.sub(r"\s+", " ", a).strip() for a in _DBLP_AUTHORS_RE.findall(block)
        ]
        doi_match = _DBLP_DOI_RE.search(block)
        doi = doi_match.group(1) if doi_match else ""
        ee_match = _DBLP_EE_RE.search(block)
        ee = ee_match.group(1) if ee_match else ""
        # arXiv 推断：从 ee 末尾的 arXiv id
        arxiv_id = ""
        if "arxiv.org/abs/" in ee:
            m = re.search(r"arxiv\.org/abs/([\w./\-]+)", ee)
            if m:
                arxiv_id = m.group(1)
        rows.append({
            "id": hit_id,
            "title": title,
            "authors": "; ".join(authors),
            "year": year,
            "venue": venue["name"],
            "kind": venue["kind"],
            "area": venue["area"],
            "area_folder": venue["area_folder"],
            "stream": venue["stream"],
            "type": "Conference and Workshop Papers" if venue["kind"] == "conf" else "Journal Articles",
            "doi": doi,
            "ee": ee,
            "arxiv_id": arxiv_id,
            "citation_count": 0,   # Stage2 填充
            "tldr": "",            # Stage2 填充
            "local_pdf": "",       # Stage3 填充
        })
    return rows


def stage1(
    years: Iterable[int],
    *,
    venues: Optional[list[str]] = None,
    resume: bool = True,
) -> dict:
    """
    Stage 1: 遍历指定 years × 指定 venues，从 DBLP 拉取论文清单，合并到 _index.csv。

    返回 {venue: count, ...}。
    """
    target_venues = [v for v in VENUES if (not venues) or v["name"] in venues]
    log(f"=== Stage1 DBLP 爬取 {min(years)}-{max(years)}, {len(target_venues)} 个 venue ===")

    # 读已有 _index.csv 用于断点续跑
    existing: dict[str, dict] = {}  # id -> row
    index_csv = ROOT / "_index.csv"
    if resume and index_csv.exists():
        with open(index_csv, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("id"):
                    existing[row["id"]] = row
        log(f"[断点续跑] 已有 {len(existing)} 条")

    counts: dict[str, int] = defaultdict(int)

    for venue in target_venues:
        for year in years:
            cache_key = f"{venue['name']}_{year}.json"
            cache_path = DBLP_CACHE / cache_key
            hits: list[dict] = []
            if resume and cache_path.exists():
                try:
                    cached = json.loads(cache_path.read_text(encoding="utf-8"))
                    if isinstance(cached, list):
                        hits = cached
                except (OSError, json.JSONDecodeError):
                    hits = []
                if hits:
                    log(f"[缓存命中] {venue['name']} {year} ({len(hits)} hits)")
            if not hits:
                hits = _dblp_search_paginated(venue["name"], year, page_size=100)
                if hits:
                    cache_path.write_text(
                        json.dumps(hits, ensure_ascii=False), encoding="utf-8"
                    )
                time.sleep(DBLP_DELAY)

            if not hits:
                log(f"[跳过] {venue['name']} {year} 拉取失败")
                continue

            n_new = 0
            for hit in hits:
                row = _dblp_hit_to_row(hit, venue, year)
                if row is None:
                    continue
                existing[row["id"]] = {**existing.get(row["id"], {}), **row}
                n_new += 1
            counts[f"{venue['name']}_{year}"] += n_new
            log(f"[{venue['name']} {year}] +{n_new}")

    # 写出 _index.csv（保留字段顺序与 README 一致）
    field_order = [
        "id", "title", "authors", "year", "venue", "kind",
        "area", "area_folder", "stream", "type", "doi",
        "ee", "arxiv_id", "citation_count", "tldr", "local_pdf",
    ]
    all_rows = list(existing.values())
    all_rows.sort(key=lambda r: r.get("id", ""))
    with open(index_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=field_order)
        writer.writeheader()
        for row in all_rows:
            writer.writerow({k: row.get(k, "") for k in field_order})
    log(f"[完成] _index.csv 共 {len(all_rows)} 行")
    return dict(counts)


# ============================================================
# Stage 2: OpenAlex 富化引用数 + 摘要
# ============================================================
def _openalex_enrich(doi_or_id: str, *, mailto: str) -> dict:
    """按 DOI 查 OpenAlex，返回 cited_by_count 与 abstract。"""
    url = f"{OPENALEX_BASE}/doi/{doi_or_id}"
    r = _request_with_backoff(
        url,
        base_delay=0.5,
        max_retries=2,
        timeout=15,
        headers={"User-Agent": f"AcademicPKM/1.0 (mailto:{mailto})"},
    )
    if r is None:
        return {"cited_by_count": 0, "abstract": ""}
    try:
        data = r.json()
    except Exception:
        return {"cited_by_count": 0, "abstract": ""}
    # OpenAlex 把 abstract 放在 inverted_index，需要还原
    inv = data.get("abstract_inverted_index") or {}
    abstract = _inverted_to_text(inv)
    return {
        "cited_by_count": data.get("cited_by_count", 0) or 0,
        "abstract": abstract,
    }


def _inverted_to_text(inv: dict) -> str:
    if not inv:
        return ""
    pos_word: list[tuple[int, str]] = []
    for word, positions in inv.items():
        for p in positions:
            pos_word.append((p, word))
    pos_word.sort()
    return " ".join(w for _, w in pos_word)


def stage2(*, mailto: Optional[str] = None) -> int:
    """
    Stage 2: 对 _index.csv 中有 DOI 的论文，调用 OpenAlex 富化。
    追加到 _abstracts.jsonl，已存在的 id 自动跳过。
    """
    mailto = mailto or os.environ.get("OPENALEX_MAILTO", "researcher@example.com")
    index_csv = ROOT / "_index.csv"
    abstracts_path = ROOT / "_abstracts.jsonl"

    if not index_csv.exists():
        log("[Stage2] 缺少 _index.csv，请先跑 stage1")
        return 0

    existing_ids: set[str] = set()
    if abstracts_path.exists():
        with open(abstracts_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    obj = json.loads(line)
                    existing_ids.add(obj.get("id", ""))
                except json.JSONDecodeError:
                    continue
    log(f"[Stage2] 已富化 {len(existing_ids)} 条")

    rows: list[dict] = []
    with open(index_csv, "r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    enriched_count = 0
    # 用 append 模式，分批写
    out_f = open(abstracts_path, "a", encoding="utf-8", buffering=1)
    try:
        for i, row in enumerate(rows):
            if not row.get("doi"):
                continue
            if row["id"] in existing_ids:
                continue
            data = _openalex_enrich(row["doi"], mailto=mailto)
            out_obj = {
                "id": row["id"],
                "title": row.get("title", ""),
                "doi": row.get("doi", ""),
                "citation_count": data["cited_by_count"],
                "abstract": data["abstract"],
            }
            out_f.write(json.dumps(out_obj, ensure_ascii=False) + "\n")
            enriched_count += 1
            row["citation_count"] = data["cited_by_count"]
            row["tldr"] = (data["abstract"][:300] + "...") if data["abstract"] else ""
            if (i + 1) % 50 == 0:
                log(f"[Stage2] 已富化 {enriched_count}/{len(rows)}")
    finally:
        out_f.close()

    # 回写 _index.csv 的 citation_count + tldr
    field_order = [
        "id", "title", "authors", "year", "venue", "kind",
        "area", "area_folder", "stream", "type", "doi",
        "ee", "arxiv_id", "citation_count", "tldr", "local_pdf",
    ]
    with open(index_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=field_order)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in field_order})

    log(f"[Stage2 完成] 新增 {enriched_count} 条")
    return enriched_count


# ============================================================
# Stage 3: 筛高分论文 + arXiv 下载 PDF
# ============================================================
def _is_high_impact(row: dict, topn_counter: dict[tuple[str, int], int]) -> bool:
    """判定一条论文是否为高分论文。

    规则：引用数 >= HIGH_MIN_CIT 或 (venue, year) 内 top HIGH_TOPN。
    """
    try:
        cit = int(row.get("citation_count") or 0)
    except ValueError:
        cit = 0
    if cit >= HIGH_MIN_CIT:
        return True
    key = (row.get("venue", ""), int(row.get("year", 0) or 0))
    rank = topn_counter.get(key, 0)
    return rank < HIGH_TOPN


def _arxiv_id_to_pdf_url(arxiv_id: str) -> str:
    # arXiv ID 形如 1706.03762 或 cs.LG/0006007
    return f"https://arxiv.org/pdf/{arxiv_id}.pdf"


def stage3(*, dry_run: bool = False) -> dict:
    """
    Stage 3: 筛高分论文 -> arXiv 下载 PDF -> 分层目录 + meta.json。

    受 PDF_CAP 限制。dry_run=True 时仅筛选不下载。
    """
    index_csv = ROOT / "_index.csv"
    if not index_csv.exists():
        log("[Stage3] 缺少 _index.csv")
        return {}

    with open(index_csv, "r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    # 统计每个 (venue, year) 的 citation 排名
    by_vy: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for row in rows:
        try:
            cit = int(row.get("citation_count") or 0)
        except ValueError:
            cit = 0
        key = (row.get("venue", ""), int(row.get("year", 0) or 0))
        by_vy[key].append({**row, "citation_count": cit})
    topn_counter: dict[tuple[str, int], int] = {}
    for key, lst in by_vy.items():
        lst.sort(key=lambda r: r["citation_count"], reverse=True)
        for i, _ in enumerate(lst):
            topn_counter[key] = i + 1  # 累计计数，仅 topN 用

    # 筛选高影响力论文
    high_impact = [
        row for row in rows
        if _is_high_impact(row, {(k, v): v for k, v in topn_counter.items()})
    ]
    high_impact.sort(key=lambda r: int(r.get("citation_count") or 0), reverse=True)
    log(f"[Stage3] 高影响力论文 {len(high_impact)} 条（PDF_CAP={PDF_CAP}）")

    # 写 _high_impact.csv
    field_order = [
        "id", "title", "authors", "year", "venue", "kind",
        "area", "area_folder", "stream", "type", "doi",
        "ee", "arxiv_id", "citation_count", "tldr", "local_pdf",
    ]
    hi_path = ROOT / "_high_impact.csv"
    with open(hi_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=field_order)
        writer.writeheader()
        for row in high_impact:
            writer.writerow({k: row.get(k, "") for k in field_order})

    # 下载 PDF
    downloaded = 0
    for row in high_impact[:PDF_CAP if not dry_run else 0]:
        arxiv_id = (row.get("arxiv_id") or "").strip()
        if not arxiv_id:
            continue
        area_folder = row.get("area_folder", "Other")
        venue = row.get("venue", "Unknown")
        year = row.get("year", "0")
        safe_title = re.sub(r'[\\/:*?"<>|]', "_", row.get("title", "untitled"))[:80]
        out_dir = ROOT / area_folder / venue / str(year) / safe_title
        out_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = out_dir / "paper.pdf"
        if pdf_path.exists():
            continue
        pdf_url = _arxiv_id_to_pdf_url(arxiv_id)
        log(f"[Stage3] 下载 {arxiv_id} -> {pdf_path}")
        r = _request_with_backoff(pdf_url, base_delay=ARXIV_DELAY, max_retries=2, timeout=30)
        if r is None or r.status_code != 200:
            continue
        pdf_path.write_bytes(r.content)
        # 写 meta.json
        meta = {
            "id": row.get("id"),
            "title": row.get("title"),
            "authors": row.get("authors"),
            "year": row.get("year"),
            "venue": row.get("venue"),
            "doi": row.get("doi"),
            "arxiv_id": arxiv_id,
            "citation_count": row.get("citation_count"),
            "tldr": row.get("tldr"),
            "local_pdf": str(pdf_path.relative_to(ROOT)),
        }
        (out_dir / "meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        downloaded += 1
        time.sleep(ARXIV_DELAY)

    log(f"[Stage3 完成] 下载 {downloaded} 篇 PDF")
    return {"high_impact_count": len(high_impact), "downloaded": downloaded}


# ============================================================
# report: 写出 _venue_report.txt
# ============================================================
def report() -> None:
    index_csv = ROOT / "_index.csv"
    if not index_csv.exists():
        log("[report] 缺少 _index.csv")
        return
    with open(index_csv, "r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    counts: dict[tuple[str, str], int] = defaultdict(int)
    for row in rows:
        key = (row.get("venue", ""), row.get("area_folder", ""))
        counts[key] += 1

    out_path = ROOT / "_venue_report.txt"
    lines = ["venue\t子领域\t论文数"]
    for venue_name, venue in VENUES_BY_NAME.items():
        n = counts.get((venue_name, venue["area_folder"]), 0)
        lines.append(f"{venue_name}\t{venue['area_folder']}\t{n}")
    lines.append(f"\n总计: {len(rows)} 篇")
    out_path.write_text("\n".join(lines), encoding="utf-8")
    log(f"[report] 写入 {out_path}")


# ============================================================
# CLI
# ============================================================
def main() -> int:
    parser = argparse.ArgumentParser(description="CCF-A 论文自动化爬取与分类存储")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("stage1", help="DBLP 爬取全量论文清单")
    p1.add_argument("--years", default=f"{DEFAULT_YEAR_START}-{DEFAULT_YEAR_END}")
    p1.add_argument("--venues", nargs="*", default=None,
                    help="只跑指定 venue（默认全部 87 个）")
    p1.add_argument("--no-resume", action="store_true")

    p2 = sub.add_parser("stage2", help="OpenAlex 富化引用数+摘要")

    p3 = sub.add_parser("stage3", help="筛高分论文+下载 PDF")
    p3.add_argument("--dry-run", action="store_true", help="只筛选不下载")

    sub.add_parser("report", help="写出 _venue_report.txt")

    pa = sub.add_parser("all", help="一键三阶段")
    pa.add_argument("--years", default=f"{DEFAULT_YEAR_START}-{DEFAULT_YEAR_END}")
    pa.add_argument("--venues", nargs="*", default=None)
    pa.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()

    if args.cmd == "stage1":
        years = _parse_years(args.years)
        stage1(years, venues=args.venues, resume=not args.no_resume)
    elif args.cmd == "stage2":
        stage2()
    elif args.cmd == "stage3":
        stage3(dry_run=args.dry_run)
    elif args.cmd == "report":
        report()
    elif args.cmd == "all":
        years = _parse_years(args.years)
        stage1(years, venues=args.venues)
        stage2()
        stage3(dry_run=args.dry_run)
        report()
    return 0


def _parse_years(spec: str) -> list[int]:
    if "-" in spec:
        a, b = spec.split("-", 1)
        return list(range(int(a), int(b) + 1))
    return [int(spec)]


if __name__ == "__main__":
    sys.exit(main())
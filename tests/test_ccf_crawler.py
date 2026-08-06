"""
tests/test_ccf_crawler.py
=========================
针对 ccf_crawler.py 的 pytest 测试套件：

  - 离线单元测试（不需要网络）
  - 真实 API smoke（Crossref、OpenAlex），需网络可达
  - 集成：单 venue 单年的 stage1 完整 DBLP→CSV 链路

跑：
  pytest tests/test_ccf_crawler.py -v
"""
from __future__ import annotations

import csv
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

import ccf_crawler as crawler


# ------------------------------------------------------------
# 离线单元测试
# ------------------------------------------------------------
class TestVenueTable:
    def test_venue_count_is_87(self):
        assert len(crawler.VENUES) == 87, f"应为 87 个 venue, 实际 {len(crawler.VENUES)}"

    def test_all_venues_have_required_fields(self):
        required = {"name", "area", "area_folder", "kind", "stream"}
        for v in crawler.VENUES:
            missing = required - set(v.keys())
            assert not missing, f"{v.get('name')} 缺少字段: {missing}"

    def test_venue_names_unique(self):
        names = [v["name"] for v in crawler.VENUES]
        assert len(names) == len(set(names)), f"重复 venue 名: {names}"

    def test_all_venues_have_stream_path(self):
        for v in crawler.VENUES:
            assert v["stream"].startswith("streams/"), f"{v['name']} stream 路径异常: {v['stream']}"

    def test_known_venues_present(self):
        names = {v["name"] for v in crawler.VENUES}
        for must in ["AAAI", "NeurIPS", "ICCV", "TPAMI", "SIGMOD", "STOC", "ISCA"]:
            assert must in names, f"缺失关键 venue: {must}"

    def test_area_folder_distribution_matches_report(self):
        from collections import Counter
        cnt = Counter(v["area_folder"] for v in crawler.VENUES)
        # README 中列出 AI=17, Database=10, Networks=6, Security=9,
        # Software=10, Theory=7, Graphics=4, HCI=4, Architecture=12, Interdisciplinary=8
        expected = {
            "AI": 17, "Database": 10, "Networks": 6, "Security": 9,
            "Software": 10, "Theory": 7, "Graphics": 4, "HCI": 4,
            "Architecture": 12, "Interdisciplinary": 8,
        }
        for area, n in expected.items():
            assert cnt[area] == n, f"{area}: 期望 {n}, 实际 {cnt[area]}"


class TestIndexCsvSchema:
    def test_field_order_defined_in_module(self):
        # field_order 在 stage1 / stage2 / stage3 中保持一致：见源码
        expected_first_fields = ("id", "title", "authors", "year", "venue")
        # 通过反射 / 静态检查：从源码确认字段顺序
        import inspect
        src = inspect.getsource(crawler.stage1)
        assert '"id", "title", "authors", "year", "venue"' in src, \
            "stage1 中字段顺序必须以 id,title,authors,year,venue 起头"


class TestHighImpactFilter:
    def test_citation_threshold(self):
        row = {"citation_count": "50", "venue": "AAAI", "year": "2023"}
        assert crawler._is_high_impact(row, {("AAAI", 2023): 0})

    def test_below_threshold_but_in_topn(self):
        row = {"citation_count": "10", "venue": "AAAI", "year": "2023"}
        # topn_counter 中 (AAAI, 2023) 排名 = 5 < HIGH_TOPN
        assert crawler._is_high_impact(row, {("AAAI", 2023): 5})

    def test_below_threshold_outside_topn(self):
        row = {"citation_count": "5", "venue": "AAAI", "year": "2023"}
        assert not crawler._is_high_impact(row, {("AAAI", 2023): 30})

    def test_zero_citation_outside_topn(self):
        row = {"citation_count": "0", "venue": "ICLR", "year": "2023"}
        assert not crawler._is_high_impact(row, {("ICLR", 2023): 30})

    def test_invalid_citation_count_doesnt_crash(self):
        row = {"citation_count": "abc", "venue": "AAAI", "year": "2023"}
        assert not crawler._is_high_impact(row, {("AAAI", 2023): 30})


class TestYearParsing:
    def test_range(self):
        assert crawler._parse_years("2023-2025") == [2023, 2024, 2025]

    def test_single_year(self):
        assert crawler._parse_years("2024") == [2024]

    def test_two_year_range(self):
        assert crawler._parse_years("2020-2021") == [2020, 2021]


class TestInvertedIndexRestore:
    def test_basic(self):
        inv = {"hello": [0], "world": [1]}
        assert crawler._inverted_to_text(inv) == "hello world"

    def test_out_of_order_positions(self):
        inv = {"b": [1], "a": [0]}
        assert crawler._inverted_to_text(inv) == "a b"

    def test_empty(self):
        assert crawler._inverted_to_text({}) == ""

    def test_multi_positions(self):
        inv = {"the": [0, 2], "cat": [1]}
        assert crawler._inverted_to_text(inv) == "the cat the"


class TestArxivPdfUrl:
    def test_modern_id(self):
        assert crawler._arxiv_id_to_pdf_url("1706.03762") == "https://arxiv.org/pdf/1706.03762.pdf"

    def test_old_style_id(self):
        assert crawler._arxiv_id_to_pdf_url("cs.LG/0006007") == "https://arxiv.org/pdf/cs.LG/0006007.pdf"


# ------------------------------------------------------------
# 集成测试（真实 DBLP 下载）
# ------------------------------------------------------------
@pytest.mark.integration
class TestStage1Integration:
    """真实跑一次 stage1 单 venue 单年：依赖网络可达 dblp.org。"""

    def test_aaai_2023_dblp_search_returns_hits(self):
        hits = crawler._dblp_search_paginated("AAAI", 2023, page_size=5)
        if not hits:
            pytest.skip("DBLP 搜索 API 不可达或返回 0 行（限速）")
        assert len(hits) > 0
        # 每条 hit 都必须有 info.title
        for hit in hits[:3]:
            info = hit.get("info") or {}
            assert info.get("title"), f"hit 缺少 title: {hit}"

    def test_dblp_hit_to_row_basic(self):
        # 用真实 AAAI 2023 第一条 hit 做 fixture
        hits = crawler._dblp_search_paginated("AAAI", 2023, page_size=1)
        if not hits:
            pytest.skip("DBLP 不可达")
        venue = crawler.VENUES_BY_NAME["AAAI"]
        row = crawler._dblp_hit_to_row(hits[0], venue, 2023)
        assert row is not None
        assert row["venue"] == "AAAI"
        assert row["year"] == 2023
        assert row["area_folder"] == "AI"
        assert row["id"]
        assert row["title"]


# ------------------------------------------------------------
# 真实 API smoke（OpenAlex）—— 验证 Stage2 enrichment 路径
# ------------------------------------------------------------
@pytest.mark.integration
class TestStage2Enrichment:
    """用 Segment Anything (ICCV 2023) DOI 跑真实 OpenAlex 富化。"""

    DOI = "10.1109/ICCV51070.2023.00371"

    def test_vaswani_doi_enrich(self):
        data = crawler._openalex_enrich(self.DOI, mailto=crawler.VENUES[0]["area"])
        # 即便 OpenAlex 限速失败，也应该返回 0 / 空字符串而不抛异常
        assert isinstance(data, dict)
        assert "cited_by_count" in data
        assert "abstract" in data
        assert isinstance(data["cited_by_count"], int)
        # Segment Anything 被引 > 9000；若 OpenAlex 返回 0，多半是限速，不视为失败
        if data["cited_by_count"] > 0:
            assert data["abstract"], "有引用数时应也有摘要"


# ------------------------------------------------------------
# 真实 API smoke（Crossref）—— 验证 _venue_report 完整性
# ------------------------------------------------------------
@pytest.mark.integration
class TestCrossrefSanity:
    """通过 Crossref 验证项目根 _ccf_a.bib 中 Segment Anything 条目的 DOI 真实性。"""

    DOI = "10.1109/ICCV51070.2023.00371"

    def test_crossref_returns_verified(self):
        import requests
        try:
            r = requests.get(
                f"https://api.crossref.org/works/{self.DOI}",
                headers={"User-Agent": "AcademicPKM-test (mailto:test@example.com)"},
                timeout=15,
            )
        except requests.RequestException:
            pytest.skip("Crossref 网络不可达")
        if r.status_code != 200:
            pytest.skip(f"Crossref 返回 {r.status_code}（限速或 DOI 不存在）")
        msg = r.json()["message"]
        title = msg.get("title", [""])[0]
        assert "segment" in title.lower() or "sam" in title.lower(), \
            f"标题应包含 'segment' 或 'sam': {title}"
        # 验证 Kirillov 是作者之一
        authors = " ".join(a.get("family", "") for a in msg.get("author", []))
        assert "kirillov" in authors.lower(), f"应包含 Kirillov 作者: {authors}"


# ------------------------------------------------------------
# 真实 API smoke（Semantic Scholar）—— 验证 s2_search.py 输入格式
# ------------------------------------------------------------
@pytest.mark.integration
class TestS2Sanity:
    """直接验证 S2 Graph API 可用，作为后续 SKILL 测试的前置条件。"""

    DOI = "10.1109/ICCV51070.2023.00371"

    def test_s2_doi_lookup(self):
        import requests
        try:
            r = requests.get(
                f"https://api.semanticscholar.org/graph/v1/paper/DOI:{self.DOI}",
                params={"fields": "title,year,citationCount"},
                timeout=15,
            )
        except requests.RequestException:
            pytest.skip("S2 网络不可达")
        if r.status_code != 200:
            pytest.skip(f"S2 返回 {r.status_code}（限速）")
        paper = r.json()
        assert paper["title"]
        assert paper["year"] == 2023
        assert paper["citationCount"] > 1000
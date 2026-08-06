"""
tests/test_skill_scripts.py
============================
针对 5 个 TRAE Skill 资源脚本的 pytest 测试：

  - crossref_verify.py（fact-checking-citations）
  - s2_verify.py（fact-checking-citations）
  - citation_graph.py（building-citation-timeline）
  - author_cluster.py（tracing-lineage-by-team）
  - s2_search.py（tracing-lineage-by-era）

策略：把每个脚本作为模块导入（路径添加到 sys.path），覆盖离线单元 + 真实 API
集成测试。集成测试用 -m "integration" 过滤，需 S2_API_KEY 的会自动 SKIP。

跑：
  pytest tests/test_skill_scripts.py -v
  pytest tests/test_skill_scripts.py -v -m integration
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / ".trae" / "skills"


def _load_module(name: str, resources_dir: Path):
    """动态加载 Skill resources 目录下的脚本作为模块。"""
    script_path = resources_dir / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, script_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# 提前加载 5 个 Skill 脚本
CROSSREF = _load_module("crossref_verify", SKILLS / "fact-checking-citations" / "resources")
S2_VERIFY = _load_module("s2_verify", SKILLS / "fact-checking-citations" / "resources")
CITATION_GRAPH = _load_module("citation_graph", SKILLS / "building-citation-timeline" / "resources")
AUTHOR_CLUSTER = _load_module("author_cluster", SKILLS / "tracing-lineage-by-team" / "resources")
S2_SEARCH = _load_module("s2_search", SKILLS / "tracing-lineage-by-era" / "resources")


# ============================================================
# crossref_verify.py
# ============================================================
class TestCrossrefVerify:
    def test_fuzzy_title_match_identical(self):
        assert CROSSREF.fuzzy_title_match("Attention Is All You Need",
                                          "Attention Is All You Need")

    def test_fuzzy_title_match_partial(self):
        # Jaccard 阈值 0.8
        s1 = "Attention Is All You Need Transformer Paper"
        s2 = "Attention Is All You Need"
        # 词集: {attention, is, all, you, need, transformer, paper} vs {attention, is, all, you, need}
        # intersection=5, union=7 -> 5/7 = 0.71 < 0.8 -> False
        assert not CROSSREF.fuzzy_title_match(s1, s2)

    def test_fuzzy_title_match_empty(self):
        assert not CROSSREF.fuzzy_title_match("", "")
        assert not CROSSREF.fuzzy_title_match("foo", "")

    def test_fuzzy_title_match_high_overlap(self):
        s = "a b c d e f g h"
        # 高重叠：只差一两个词
        assert CROSSREF.fuzzy_title_match(s, "a b c d e f g h i j")

    @pytest.mark.integration
    def test_verify_by_doi_real(self):
        r = CROSSREF.verify_by_doi("10.1109/ICCV51070.2023.00371")  # Segment Anything
        if r.get("status") != "VERIFIED":
            pytest.skip(f"Crossref 不可达: {r}")
        assert r["title"]
        assert "segment" in r["title"].lower() or "sam" in r["title"].lower()
        authors = " ".join(r.get("authors") or [])
        assert "kirillov" in authors.lower()


# ============================================================
# s2_verify.py
# ============================================================
class TestS2Verify:
    def test_module_imports(self):
        # 仅断言关键函数存在
        assert hasattr(S2_VERIFY, "verify_by_doi")
        assert hasattr(S2_VERIFY, "search_by_title")
        assert hasattr(S2_VERIFY, "claim_supported_by_paper")
        assert hasattr(S2_VERIFY, "check_reference_relationship")
        assert hasattr(S2_VERIFY, "batch_verify")

    def test_paper_fields_defined(self):
        # 验证请求字段包含 title/citationCount 等核心字段
        assert "title" in S2_VERIFY.PAPER_FIELDS
        assert "citationCount" in S2_VERIFY.PAPER_FIELDS
        assert "abstract" in S2_VERIFY.PAPER_FIELDS

    @pytest.mark.integration
    def test_verify_by_doi_real(self):
        r = S2_VERIFY.verify_by_doi("10.1109/ICCV51070.2023.00371")
        if r.get("status") != "VERIFIED":
            pytest.skip(f"S2 不可达: {r}")
        assert r["title"]
        assert r["year"] == 2023
        assert r["citationCount"] > 1000

    @pytest.mark.integration
    def test_search_by_title_real(self):
        results = S2_VERIFY.search_by_title("Segment Anything", limit=3)
        if not results:
            pytest.skip("S2 search 端点限速（429），属于预期降级路径")
        assert len(results) >= 1
        first = results[0]
        assert "title" in first


# ============================================================
# citation_graph.py
# ============================================================
class TestCitationGraph:
    def test_aggregate_by_year_basic(self):
        papers = [
            {"year": 2023, "title": "A"},
            {"year": 2023, "title": "B"},
            {"year": 2024, "title": "C"},
            {"year": None, "title": "D"},  # 应进 unknown 桶
        ]
        result = CITATION_GRAPH.aggregate_by_year(papers)
        assert result["total"] == 4
        assert "2023" in result["byYear"]
        assert len(result["byYear"]["2023"]) == 2
        assert "unknown" in result["byYear"]
        assert len(result["byYear"]["unknown"]) == 1

    def test_aggregate_by_year_empty(self):
        result = CITATION_GRAPH.aggregate_by_year([])
        assert result["total"] == 0
        assert result["yearRange"] is None

    def test_aggregate_by_year_range(self):
        papers = [
            {"year": 2018, "title": "A"},
            {"year": 2023, "title": "B"},
        ]
        result = CITATION_GRAPH.aggregate_by_year(papers)
        assert result["yearRange"] == [2018, 2023]

    def test_mark_key_turning_points_top_k(self):
        papers = [
            {"influentialCitationCount": 100, "title": "top1"},
            {"influentialCitationCount": 50, "title": "top2"},
            {"influentialCitationCount": 10, "title": "top3"},
            {"influentialCitationCount": 0, "title": "low"},
        ]
        flagged = CITATION_GRAPH.mark_key_turning_points(papers, top_k=2, influ_threshold=5)
        # top_k=2: 排前 2 的必选；influ>=5 的也选
        # 100 >= 5 -> in; 50 >= 5 -> in; 10 >= 5 -> in; 0 < 5 -> out
        assert len(flagged) == 3
        # 排序：influentialCitationCount 降序
        assert flagged[0]["title"] == "top1"
        assert flagged[1]["title"] == "top2"
        assert flagged[2]["title"] == "top3"
        for p in flagged:
            assert p["isKeyTurningPoint"] is True

    def test_normalize_paper_basic(self):
        paper = {
            "title": "Foo",
            "year": 2023,
            "externalIds": {"DOI": "10.1234/abc", "ArXiv": "2301.00001", "CorpusId": "12345"},
            "authors": [{"name": "Alice"}, {"name": "Bob"}],
        }
        out = CITATION_GRAPH._normalize_paper(paper)
        assert out["doi"] == "10.1234/abc"
        assert out["arxiv"] == "2301.00001"
        assert out["corpusId"] == "12345"
        assert out["authorNames"] == ["Alice", "Bob"]


# ============================================================
# author_cluster.py
# ============================================================
class TestAuthorCluster:
    def test_normalize_paper_basic(self):
        raw = {
            "paperId": "abc123",
            "title": "Foo",
            "year": 2023,
            "externalIds": {"DOI": "10.1/abc", "ArXiv": "2301.00001"},
            "authors": [{"authorId": "1", "name": "Alice"}, {"authorId": "2", "name": "Bob"}],
            "citationCount": 100,
            "venue": "ICCV",
        }
        out = AUTHOR_CLUSTER.normalize_paper(raw, focal_author_id="1")
        assert out["paperId"] == "abc123"
        assert out["doi"] == "10.1/abc"
        assert out["arxivId"] == "2301.00001"
        assert len(out["coauthors"]) == 2
        # focal author 标记
        alice = next(c for c in out["coauthors"] if c["name"] == "Alice")
        assert alice["isFocal"] is True
        bob = next(c for c in out["coauthors"] if c["name"] == "Bob")
        assert bob["isFocal"] is False

    def test_sort_by_year_ascending(self):
        papers = [
            {"year": 2024, "citationCount": 50, "title": "B"},
            {"year": None, "citationCount": 100, "title": "Z"},
            {"year": 2020, "citationCount": 200, "title": "A"},
        ]
        sorted_p = AUTHOR_CLUSTER.sort_by_year(papers)
        # 无 year 排末尾（year_key=99999）
        assert sorted_p[0]["title"] == "A"  # 2020
        assert sorted_p[1]["title"] == "B"  # 2024
        assert sorted_p[2]["title"] == "Z"  # None -> 99999

    def test_sort_by_year_same_year_by_citation(self):
        papers = [
            {"year": 2023, "citationCount": 10, "title": "low"},
            {"year": 2023, "citationCount": 100, "title": "high"},
        ]
        sorted_p = AUTHOR_CLUSTER.sort_by_year(papers)
        assert sorted_p[0]["title"] == "high"  # 同年引用降序

    def test_build_coauthor_stats(self):
        papers = [
            {
                "year": 2023,
                "coauthors": [
                    {"name": "Alice", "authorId": "1"},
                    {"name": "Bob", "authorId": "2"},
                ],
            },
            {
                "year": 2024,
                "coauthors": [
                    {"name": "Alice", "authorId": "1"},
                    {"name": "Charlie", "authorId": "3"},
                ],
            },
        ]
        stats = AUTHOR_CLUSTER.build_coauthor_stats(papers, focal_author_id="0")
        # 计数：Alice=2, Bob=1, Charlie=1
        names_count = {s["name"]: s["collaborations"] for s in stats}
        assert names_count["Alice"] == 2
        assert names_count["Bob"] == 1
        assert names_count["Charlie"] == 1


# ============================================================
# s2_search.py
# ============================================================
class TestS2Search:
    def test_paper_fields_default(self):
        assert "title" in S2_SEARCH.DEFAULT_FIELDS
        assert "citationCount" in S2_SEARCH.DEFAULT_FIELDS
        assert "abstract" in S2_SEARCH.DEFAULT_FIELDS
        assert "embedding.specter_v2" in S2_SEARCH.DEFAULT_FIELDS

    def test_hard_cap_constant(self):
        assert S2_SEARCH.HARD_CAP == 1000
        assert S2_SEARCH.PAGE_SIZE == 100

    def test_normalize_paper_basic(self):
        paper = {
            "title": "Foo",
            "externalIds": {"DOI": "10.1234/abc", "ArXiv": "2301.00001"},
        }
        out = S2_SEARCH._normalize_paper(paper)
        assert out["doi"] == "10.1234/abc"
        assert out["arxiv"] == "2301.00001"
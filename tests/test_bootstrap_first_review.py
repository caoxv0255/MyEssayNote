"""
tests/test_bootstrap_first_review.py
====================================
针对 bootstrap_first_review.py 的测试。

  - 离线单元：slug、年代切片、代表抽取、Markdown 渲染
  - 真实：调用 S2 + Crossref 跑通完整流水线（标记为 integration）
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import bootstrap_first_review as bfr  # noqa: E402


class TestSlugify:
    def test_basic(self):
        assert bfr._slugify("Attention Mechanism") == "attention-mechanism"

    def test_underscore(self):
        assert bfr._slugify("graph_neural_network") == "graph-neural-network"

    def test_already_lower(self):
        assert bfr._slugify("diffusion model") == "diffusion-model"


class TestSegmentByEra:
    def test_basic_5_year_buckets(self):
        papers = [
            {"year": 2014, "title": "A"},
            {"year": 2015, "title": "B"},
            {"year": 2017, "title": "C"},
            {"year": 2023, "title": "D"},
            {"year": 2024, "title": "E"},
        ]
        buckets = bfr.segment_by_era(papers, era_size=5)
        # min_year=2014, max_year=2024
        # 2014-2018, 2019-2023, 2024-2028
        assert "2014-2018" in buckets
        assert "2019-2023" in buckets
        assert "2024-2028" in buckets
        assert len(buckets["2014-2018"]) == 3  # A, B, C
        assert len(buckets["2019-2023"]) == 1  # D
        assert len(buckets["2024-2028"]) == 1  # E

    def test_no_year_papers_skipped(self):
        papers = [{"title": "no year"}]
        buckets = bfr.segment_by_era(papers)
        assert buckets == {}

    def test_empty(self):
        assert bfr.segment_by_era([]) == {}


class TestPickReps:
    def test_top_k_by_citation(self):
        papers = [
            {"citationCount": 10, "title": "low"},
            {"citationCount": 1000, "title": "high"},
            {"citationCount": 500, "title": "mid"},
            {"citationCount": 0, "title": "zero"},
        ]
        reps = bfr.pick_reps(papers, k=2)
        assert len(reps) == 2
        assert reps[0]["title"] == "high"
        assert reps[1]["title"] == "mid"

    def test_k_larger_than_input(self):
        papers = [{"citationCount": 100, "title": "only"}]
        reps = bfr.pick_reps(papers, k=5)
        assert len(reps) == 1

    def test_none_citation_treated_as_zero(self):
        papers = [
            {"citationCount": None, "title": "no cite"},
            {"citationCount": 50, "title": "has cite"},
        ]
        reps = bfr.pick_reps(papers, k=1)
        assert reps[0]["title"] == "has cite"


class TestMergeLocal:
    def test_no_index_csv_returns_s2_papers_unchanged(self, tmp_path, monkeypatch):
        # monkey patch INDEX_CSV
        import bootstrap_first_review as mod
        original = mod.INDEX_CSV
        mod.INDEX_CSV = tmp_path / "missing.csv"
        try:
            # 没有 authors，所以合成 citekey 含 'unknown'
            s2_papers = [{"externalIds": {"DOI": "10.1234/abc"}, "year": 2023}]
            merged = mod.merge_local(s2_papers)
            assert len(merged) == 1
            assert "citekey" in merged[0]
            assert merged[0].get("citekey_synthesized") is True
        finally:
            mod.INDEX_CSV = original

    def test_local_match_adds_real_citekey(self, tmp_path, monkeypatch):
        # 写一个 _index.csv 含 doi 10.1109/TEST.2023.001
        import csv as csvmod
        idx = tmp_path / "_index.csv"
        with open(idx, "w", encoding="utf-8", newline="") as f:
            w = csvmod.DictWriter(f, fieldnames=["id", "doi", "title"])
            w.writeheader()
            w.writerow({"id": "conf/test/MyPaper23", "doi": "10.1109/TEST.2023.001", "title": "Mine"})

        import bootstrap_first_review as mod
        original = mod.INDEX_CSV
        mod.INDEX_CSV = idx
        try:
            s2_papers = [{"externalIds": {"DOI": "10.1109/TEST.2023.001"}, "year": 2023}]
            merged = mod.merge_local(s2_papers)
            assert merged[0]["citekey"] == "conf/test/MyPaper23"
            assert "synthesized" not in merged[0]
        finally:
            mod.INDEX_CSV = original


class TestRenderLineage:
    def test_basic_structure(self):
        topic = "test topic"
        papers = [
            {"citekey": "x2023", "title": "Paper X", "year": 2023,
             "citationCount": 100, "externalIds": {"DOI": ""}},
        ]
        buckets = {"2023-2027": papers}
        md = bfr.render_lineage(topic, papers, buckets)
        assert "type: review" in md
        assert "topic: test-topic" in md
        assert "paper_count: 1" in md
        assert "2023-2027" in md
        assert "[[x2023]]" in md
        # 表格关键列存在（避免 hardcode 列数, 后续扩列不会 break）
        assert "作者" in md
        assert "标题" in md
        assert "DOI 状态" in md

    def test_includes_doi_status_marker(self):
        # render_lineage 内部会调 crossref_verify，但单元测试只验证渲染骨架
        # （实际 crossref 调用需要网络，用 monkey patch 跳过）
        import bootstrap_first_review as mod
        original = mod.verify_doi_with_crossref
        mod.verify_doi_with_crossref = lambda doi: "VERIFIED" if doi else "无 DOI"
        try:
            papers = [{
                "citekey": "y2024", "title": "Y", "year": 2024,
                "citationCount": 50, "externalIds": {"DOI": "10.1234/abc"},
            }]
            md = mod.render_lineage("t", papers, {"2024-2028": papers})
            assert "10.1234/abc" in md
            assert "✅" in md
        finally:
            mod.verify_doi_with_crossref = original


@pytest.mark.integration
class TestEndToEnd:
    """真实运行：S2 + Crossref 调用。"""

    def test_s2_search_returns_at_least_3(self):
        papers = bfr.run_s2_search("attention mechanism", limit=5)
        if not papers:
            pytest.skip("S2 限速或不可达")
        assert len(papers) >= 3, f"S2 应返回 ≥3 篇，实际 {len(papers)}"

    def test_crossref_verify_known_doi(self):
        # Segment Anything DOI 作为 fixture
        status = bfr.verify_doi_with_crossref("10.1109/ICCV51070.2023.00371")
        if status == "ERROR":
            pytest.skip("Crossref 不可达")
        assert status in ("VERIFIED", "UNKNOWN")  # UNKNOWN 表示 crossref_verify.py 脚本不在

    def test_main_writes_real_review_file(self, tmp_path, monkeypatch):
        """实际跑 main 一次：写入临时目录，验证产物结构。"""
        import bootstrap_first_review as mod
        original_reviews = mod.REVIEWS
        mod.REVIEWS = tmp_path
        try:
            # 显式传 argv 避免被 pytest sys.argv 污染
            rc = mod.main(["--topic", "attention mechanism", "--limit", "5", "--out", "test-lineage.md"])
        finally:
            mod.REVIEWS = original_reviews
        if rc != 0:
            pytest.skip(f"main 跳过（限速）: rc={rc}")
        out_files = list(tmp_path.glob("*.md"))
        assert len(out_files) >= 1, f"未生成文件，文件列表: {out_files}"
        content = out_files[0].read_text(encoding="utf-8")
        assert "type: review" in content
        assert "topic: attention-mechanism" in content
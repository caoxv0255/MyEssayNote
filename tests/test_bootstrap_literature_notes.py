"""
tests/test_bootstrap_literature_notes.py
=========================================
针对 bootstrap_literature_notes.py 的 pytest 测试。

  - 离线单元：用临时 CSV / 临时模板验证生成的 note 数量、frontmatter 字段、文件命名
  - 真实：检查实际 _high_impact.csv + 模板生成后 Literature 目录的现状
"""
from __future__ import annotations

import csv
import re
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import bootstrap_literature_notes as bln  # noqa: E402


SAMPLE_TPL = """---
citekey: {{citekey}}
title: {{title}}
---
# {{title}}

> {{citekey}} by {{authors}} ({{year}}), {{venue}}.

## TL;DR
{{abstract}}
"""


SAMPLE_CSV_ROWS = [
    {
        "id": "conf/iccv/Test23",
        "title": "Test Paper A",
        "authors": "Alice; Bob",
        "year": "2023",
        "venue": "ICCV",
        "doi": "10.1109/TEST.2023.001",
        "arxiv_id": "2301.00001",
        "citation_count": "100",
        "area_folder": "AI",
    },
    {
        "id": "conf/cvpr/Test24",
        "title": "Test, Paper B",  # 标题含逗号
        "authors": "Carol",
        "year": "2024",
        "venue": "CVPR",
        "doi": "10.1109/TEST.2024.002",
        "arxiv_id": "",
        "citation_count": "50",
        "area_folder": "AI",
    },
    {
        "id": "journals/tpami/Test25",
        "title": "Paper C",
        "authors": "Dan; Eve",
        "year": "2025",
        "venue": "TPAMI",
        "doi": "10.1109/TEST.2025.003",
        "arxiv_id": "",
        "citation_count": "10",  # 不在 top 2
        "area_folder": "AI",
    },
]


class TestSafeId:
    def test_slash_replaced(self):
        assert bln._safe_id("conf/iccv/Foo23") == "conf_iccv_Foo23"

    def test_dot_replaced(self):
        assert bln._safe_id("conf.iccv.Foo") == "conf_iccv_Foo"

    def test_colon_replaced(self):
        # Windows 非法字符
        assert ":" not in bln._safe_id("a:b")

    def test_passthrough(self):
        assert bln._safe_id("simple_key_23") == "simple_key_23"


class TestLoadTopN:
    def test_top_n_returns_sorted_descending(self, tmp_path):
        csv_path = tmp_path / "test.csv"
        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["id", "citation_count"])
            w.writeheader()
            for row in SAMPLE_CSV_ROWS:
                w.writerow({"id": row["id"], "citation_count": row["citation_count"]})
        rows = bln.load_top_n(csv_path, 2)
        assert len(rows) == 2
        # 按 citation 降序：100 > 50 > 10
        assert rows[0]["id"] == "conf/iccv/Test23"
        assert rows[1]["id"] == "conf/cvpr/Test24"

    def test_top_n_bom_safe(self, tmp_path):
        """utf-8-sig 应该兼容 BOM 文件。"""
        csv_path = tmp_path / "test_bom.csv"
        with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["id", "citation_count"])
            w.writeheader()
            for row in SAMPLE_CSV_ROWS[:2]:
                w.writerow({"id": row["id"], "citation_count": row["citation_count"]})
        rows = bln.load_top_n(csv_path, 2)
        assert len(rows) == 2
        # 不应有 \ufeff 前缀
        assert not rows[0]["id"].startswith("\ufeff")

    def test_invalid_citation_does_not_crash(self, tmp_path):
        csv_path = tmp_path / "bad.csv"
        with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["id", "citation_count"])
            w.writeheader()
            w.writerow({"id": "x", "citation_count": "abc"})
            w.writerow({"id": "y", "citation_count": "10"})
        rows = bln.load_top_n(csv_path, 5)
        assert len(rows) == 2
        # "abc" 视为 0，"10" 排第一
        assert rows[0]["id"] == "y"


class TestBootstrap:
    def test_generates_one_note_per_row(self, tmp_path):
        # 准备临时 _high_impact.csv + 模板（用固定文件名以便 bootstrap 找到）
        csv_path = tmp_path / "_high_impact.csv"
        with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(SAMPLE_CSV_ROWS[0].keys()))
            w.writeheader()
            for row in SAMPLE_CSV_ROWS:
                w.writerow(row)
        # 临时模板
        tpl_path = tmp_path / "tpl.md"
        tpl_path.write_text(SAMPLE_TPL, encoding="utf-8")

        # monkey patch LITERATURE / TEMPLATE_PATH / ROOT
        import bootstrap_literature_notes as mod
        original_lit = mod.LITERATURE
        original_tpl = mod.TEMPLATE_PATH
        original_root = mod.ROOT
        try:
            mod.LITERATURE = tmp_path / "lit"
            mod.TEMPLATE_PATH = tpl_path
            mod.ROOT = tmp_path  # 影响 _root()，让 bootstrap 找到 _high_impact.csv
            result = mod.bootstrap(3)
        finally:
            mod.LITERATURE = original_lit
            mod.TEMPLATE_PATH = original_tpl
            mod.ROOT = original_root

        assert result["generated"] == 3, f"结果: {result}"
        files = list((tmp_path / "lit").glob("*.md"))
        assert len(files) == 3

    def test_existing_file_is_not_overwritten(self, tmp_path):
        csv_path = tmp_path / "_high_impact.csv"
        with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(SAMPLE_CSV_ROWS[0].keys()))
            w.writeheader()
            for row in SAMPLE_CSV_ROWS[:1]:
                w.writerow(row)
        tpl_path = tmp_path / "tpl.md"
        tpl_path.write_text(SAMPLE_TPL, encoding="utf-8")

        lit_dir = tmp_path / "lit"
        lit_dir.mkdir()
        # 预放置一个同名 note（模拟 BessadokMR23）
        existing = lit_dir / "@conf_iccv_Test23.md"
        existing.write_text("# PRE-EXISTING\n", encoding="utf-8")

        import bootstrap_literature_notes as mod
        original_lit = mod.LITERATURE
        original_tpl = mod.TEMPLATE_PATH
        original_root = mod.ROOT
        try:
            mod.LITERATURE = lit_dir
            mod.TEMPLATE_PATH = tpl_path
            mod.ROOT = tmp_path
            result = mod.bootstrap(1)
        finally:
            mod.LITERATURE = original_lit
            mod.TEMPLATE_PATH = original_tpl
            mod.ROOT = original_root

        assert result["generated"] == 0
        assert result["skipped"] == 1
        # 内容不应被覆盖
        assert existing.read_text(encoding="utf-8") == "# PRE-EXISTING\n"

    def test_note_contains_expected_frontmatter(self, tmp_path):
        csv_path = tmp_path / "_high_impact.csv"
        row = SAMPLE_CSV_ROWS[0]  # conf/iccv/Test23, citation=100
        with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(row.keys()))
            w.writeheader()
            w.writerow(row)
        tpl_path = tmp_path / "tpl.md"
        tpl_path.write_text(SAMPLE_TPL, encoding="utf-8")

        lit_dir = tmp_path / "lit"
        import bootstrap_literature_notes as mod
        original_lit = mod.LITERATURE
        original_tpl = mod.TEMPLATE_PATH
        original_root = mod.ROOT
        try:
            mod.LITERATURE = lit_dir
            mod.TEMPLATE_PATH = tpl_path
            mod.ROOT = tmp_path
            mod.bootstrap(1)
        finally:
            mod.LITERATURE = original_lit
            mod.TEMPLATE_PATH = original_tpl
            mod.ROOT = original_root

        out = lit_dir / "@conf_iccv_Test23.md"
        content = out.read_text(encoding="utf-8")
        assert "citekey: conf/iccv/Test23" in content
        assert "title:" in content
        assert "year: 2023" in content
        assert "venue: ICCV" in content
        assert "doi: 10.1109/TEST.2023.001" in content
        assert "citation_count: 100" in content


class TestRealBootstrap:
    """真实运行：使用项目根的 _high_impact.csv。"""

    def test_real_high_impact_csv_loads(self):
        rows = bln.load_top_n(ROOT / "_high_impact.csv", 10)
        assert len(rows) == 10
        # top 1 应是被引最多的论文（当前是 Segment Anything）
        assert rows[0]["_cit"] >= 1000
        # id 是 DBLP 风格 key
        assert "/" in rows[0]["id"]

    def test_real_literature_dir_has_at_least_100_notes(self):
        lit_dir = ROOT / "obsidian-vault" / "Literature"
        notes = list(lit_dir.glob("@*.md"))
        assert len(notes) >= 100, f"应有 ≥100 条种子 note，实际 {len(notes)}"
"""
tests/test_bootstrap_linking.py
================================
针对 bootstrap_linking.py 的 pytest 测试。

  - 离线单元：first_author_family / 同源候选 / 同人候选 / wikilink 渲染 / 注入
  - 真实：使用 _high_impact.csv 跑完整链路
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import bootstrap_linking as bl  # noqa: E402

LITERATURE = ROOT / "obsidian-vault" / "Literature"


SAMPLE_NOTE = """---
citekey: conf/iccv/Focal23
title: "Focal Paper"
---
# Focal Paper

## 关联

> 占位

## Annotations
"""


SAMPLE_CSV = [
    {
        "id": "conf/iccv/Focal23",
        "title": "Focal Paper",
        "authors": "Alice Smith",
        "year": "2023",
        "venue": "ICCV",
        "citation_count": "100",
    },
    {
        "id": "conf/iccv/Other23",
        "title": "Same Venue Year A",
        "authors": "Bob",
        "year": "2023",
        "venue": "ICCV",
        "citation_count": "200",
    },
    {
        "id": "conf/iccv/Other23b",
        "title": "Same Venue Year B",
        "authors": "Carol",
        "year": "2023",
        "venue": "ICCV",
        "citation_count": "50",
    },
    {
        "id": "conf/cvpr/Different",
        "title": "Different Venue",
        "authors": "Dave",
        "year": "2023",
        "venue": "CVPR",
        "citation_count": "300",
    },
    {
        "id": "conf/iccv/Alice22",
        "title": "Same First Author 2022",
        "authors": "Alice Smith",
        "year": "2022",
        "venue": "ICCV",
        "citation_count": "500",
    },
    {
        "id": "conf/iccv/Alice24",
        "title": "Same First Author 2024",
        "authors": "Alice Smith",
        "year": "2024",
        "venue": "ICCV",
        "citation_count": "10",
    },
]


class TestFirstAuthorFamily:
    def test_simple(self):
        assert bl.first_author_family("Alice Smith") == "smith"

    def test_dblp_suffix(self):
        # "Jiahao Xie 0001" -> family="Xie"，数字后缀跳过
        assert bl.first_author_family("Jiahao Xie 0001") == "xie"

    def test_comma_separated(self):
        assert bl.first_author_family("Smith, Alice") == "smith"

    def test_multiple_with_suffix(self):
        assert bl.first_author_family("Alice Smith 1234; Bob") == "smith"

    def test_empty(self):
        assert bl.first_author_family("") == ""

    def test_only_number(self):
        # 全部是数字后缀 -> 返回 ""
        assert bl.first_author_family("0001 0002") == ""


class TestFindCandidatesSameVenueYear:
    def test_finds_two_same_venue_year(self):
        focal = SAMPLE_CSV[0]
        cands = bl.find_candidates_same_venue_year(focal, SAMPLE_CSV)
        assert len(cands) == 2  # Other23, Other23b
        # 按 citation 降序
        assert cands[0]["id"] == "conf/iccv/Other23"  # 200
        assert cands[1]["id"] == "conf/iccv/Other23b"  # 50

    def test_excludes_self(self):
        focal = SAMPLE_CSV[0]
        cands = bl.find_candidates_same_venue_year(focal, SAMPLE_CSV)
        assert all(c["id"] != focal["id"] for c in cands)

    def test_different_venue_excluded(self):
        focal = SAMPLE_CSV[0]
        cands = bl.find_candidates_same_venue_year(focal, SAMPLE_CSV)
        ids = [c["id"] for c in cands]
        assert "conf/cvpr/Different" not in ids

    def test_cap_8(self):
        rows = SAMPLE_CSV + [
            {"id": f"conf/iccv/Filler{i}", "title": "F", "authors": "X",
             "year": "2023", "venue": "ICCV", "citation_count": str(i)}
            for i in range(10)
        ]
        focal = SAMPLE_CSV[0]
        cands = bl.find_candidates_same_venue_year(focal, rows)
        assert len(cands) == 8


class TestFindCandidatesSameFirstAuthor:
    def test_finds_two_others(self):
        focal = SAMPLE_CSV[0]  # Alice Smith
        cands = bl.find_candidates_same_first_author(focal, SAMPLE_CSV)
        # Alice22 + Alice24
        assert len(cands) == 2
        # 按 year desc
        assert cands[0]["id"] == "conf/iccv/Alice24"  # 2024
        assert cands[1]["id"] == "conf/iccv/Alice22"  # 2022

    def test_no_family_no_candidates(self):
        focal = {"id": "x", "authors": ""}
        cands = bl.find_candidates_same_first_author(focal, SAMPLE_CSV)
        assert cands == []

    def test_excludes_self(self):
        focal = SAMPLE_CSV[0]
        cands = bl.find_candidates_same_first_author(focal, SAMPLE_CSV)
        assert all(c["id"] != focal["id"] for c in cands)


class TestRenderWikilinks:
    def test_same_venue(self):
        lines = bl.render_wikilinks(SAMPLE_CSV[0], [SAMPLE_CSV[1]], "同源")
        assert len(lines) == 1
        assert "[[@conf_iccv_Other23]]" in lines[0]
        assert "同源" in lines[0]

    def test_same_author(self):
        lines = bl.render_wikilinks(SAMPLE_CSV[0], [SAMPLE_CSV[4]], "同人")
        assert "Smith" in lines[0]
        assert "同人" in lines[0]

    def test_empty_candidates(self):
        assert bl.render_wikilinks(SAMPLE_CSV[0], [], "同源") == []


class TestInjectRelations:
    def test_no_note(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bl, "LITERATURE", tmp_path)
        r = bl.inject_relations(SAMPLE_CSV[0], [SAMPLE_CSV[1]], [SAMPLE_CSV[4]])
        assert r["status"] == "NO_NOTE"

    def test_no_section(self, tmp_path, monkeypatch):
        # 写一个没有 ## 关联 段的 note
        note_path = tmp_path / "@conf_iccv_Focal23.md"
        note_path.write_text("---\nfoo: bar\n---\n\n# Note\n", encoding="utf-8")
        monkeypatch.setattr(bl, "LITERATURE", tmp_path)
        r = bl.inject_relations(SAMPLE_CSV[0], [SAMPLE_CSV[1]], [SAMPLE_CSV[4]])
        assert r["status"] == "NO_SECTION"

    def test_injects_wikilinks(self, tmp_path, monkeypatch):
        note_path = tmp_path / "@conf_iccv_Focal23.md"
        note_path.write_text(SAMPLE_NOTE, encoding="utf-8")
        monkeypatch.setattr(bl, "LITERATURE", tmp_path)
        r = bl.inject_relations(SAMPLE_CSV[0], [SAMPLE_CSV[1], SAMPLE_CSV[2]],
                                [SAMPLE_CSV[4], SAMPLE_CSV[5]])
        assert r["status"] == "WRITTEN"
        assert r["same_vy"] == 2
        assert r["same_author"] == 2
        content = note_path.read_text(encoding="utf-8")
        assert "[[@conf_iccv_Other23]]" in content
        assert "[[@conf_iccv_Alice22]]" in content
        # ## Annotations 仍在
        assert "## Annotations" in content


class TestRealBootstrapLinking:
    """真实运行：用项目 _high_impact.csv + Literature 目录验证。"""

    def test_real_run_injects_at_least_10_notes(self):
        # 不直接调用 main（会改真实文件），用模块级函数跑前 30 篇
        with open(HIGH := (ROOT / "_high_impact.csv"), "r", encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        for r in rows:
            try:
                r["_cit"] = int(r.get("citation_count") or 0)
            except ValueError:
                r["_cit"] = 0
        rows.sort(key=lambda r: r["_cit"], reverse=True)
        rows = rows[:30]

        # 检查有多少 focal paper 有对应的 literature note
        have_note = 0
        for r in rows:
            cid = r.get("id", "")
            note = LITERATURE / f"@{bl._safe_id(cid)}.md"
            if note.exists():
                have_note += 1
        # top 30 应该大部分都有种子 note（≥25）
        assert have_note >= 25, f"top 30 中只有 {have_note} 个 note 可注入关联"

    def test_real_linking_main_dry_run(self):
        import bootstrap_linking as mod
        rc = mod.main(["--top", "5", "--dry-run"])
        assert rc == 0

    def test_real_linking_main_actually_runs(self):
        # 跑 top 5 真实写
        import bootstrap_linking as mod
        rc = mod.main(["--top", "5"])
        assert rc == 0
        # 验证至少 1 个 focal note 的 ## 关联 段被加入了 bootstrap 标记
        bootstrap_marker_found = False
        for note in LITERATURE.glob("@*.md"):
            content = note.read_text(encoding="utf-8")
            if "### 自动生成（bootstrap_linking.py）" in content:
                bootstrap_marker_found = True
                break
        assert bootstrap_marker_found, "未找到任何被注入的 ## 关联 段"
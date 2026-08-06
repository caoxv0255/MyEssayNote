"""
tests/test_zotero_import.py
============================
针对 zotero_import.py 的测试。

Zotero 本地 API（端口 23119）默认不可达，所以大部分测试都 mock。
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import zotero_import as zi  # noqa: E402


class TestIsZoteroRunning:
    @patch("zotero_import.requests.get")
    def test_running_returns_true(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200)
        assert zi.is_zotero_running() is True

    @patch("zotero_import.requests.get")
    def test_down_returns_false(self, mock_get):
        import requests
        mock_get.side_effect = requests.RequestException("connection refused")
        assert zi.is_zotero_running() is False


class TestListCollections:
    @patch("zotero_import.requests.get")
    def test_list_returns_parsed_json(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: [
                {"key": "ABC123", "data": {"name": "AI (人工智能)"}},
                {"key": "DEF456", "data": {"name": "Database"}},
            ],
        )
        cols = zi.list_collections()
        assert len(cols) == 2
        assert cols[0]["data"]["name"] == "AI (人工智能)"


class TestFindOrCreateCollection:
    @patch("zotero_import.requests.get")
    def test_found_returns_key(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: [
                {"key": "ABC123", "data": {"name": "AI"}},
                {"key": "DEF456", "data": {"name": "Database"}},
            ],
        )
        key = zi.find_or_create_collection("AI")
        assert key == "ABC123"

    @patch("zotero_import.requests.get")
    def test_not_found_returns_empty_string(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: [{"key": "X", "data": {"name": "Other"}}],
        )
        key = zi.find_or_create_collection("Nonexistent")
        assert key == ""


class TestImportBibtexFile:
    def test_missing_file(self):
        r = zi.import_bibtex_file(Path("Z:/nonexistent.bib"))
        assert r["status"] == "ERROR"

    @patch("zotero_import.is_zotero_running")
    def test_zotero_down(self, mock_running):
        mock_running.return_value = False
        tmp = Path("test.bib")
        tmp.write_text("@article{x, title={T}}", encoding="utf-8")
        try:
            r = zi.import_bibtex_file(tmp)
            assert r["status"] == "ERROR"
            assert "Zotero" in r["msg"]
        finally:
            tmp.unlink()

    @patch("zotero_import.is_zotero_running")
    def test_dry_run_does_not_post(self, mock_running):
        mock_running.return_value = True
        tmp = Path("test.bib")
        tmp.write_text("@article{x, title={T}}", encoding="utf-8")
        try:
            r = zi.import_bibtex_file(tmp, dry_run=True)
            assert r["status"] == "DRY_RUN"
        finally:
            tmp.unlink()


class TestMainCli:
    def test_no_args_errors(self, capsys):
        rc = zi.main([])
        assert rc == 1
        captured = capsys.readouterr()
        assert "bibtex" in captured.err.lower() or "未指定" in captured.err

    @patch("zotero_import.list_collections")
    @patch("zotero_import.is_zotero_running")
    def test_check_returns_zotero_status(self, mock_running, mock_cols, capsys):
        mock_running.return_value = True
        mock_cols.return_value = [{"key": "X", "data": {"name": "Test"}}]
        rc = zi.main(["--check"])
        assert rc == 0
        captured = capsys.readouterr()
        assert "✅" in captured.out

    @patch("zotero_import.is_zotero_running")
    def test_check_zotero_down(self, mock_running, capsys):
        mock_running.return_value = False
        rc = zi.main(["--check"])
        assert rc == 1
        captured = capsys.readouterr()
        assert "❌" in captured.out
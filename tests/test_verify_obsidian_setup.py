"""
tests/test_verify_obsidian_setup.py
====================================
针对 verify_obsidian_setup.py 的测试。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import verify_obsidian_setup as vos  # noqa: E402


def test_required_plugins_defined():
    assert "zotlit" in vos.REQUIRED_PLUGINS
    assert "dataview" in vos.REQUIRED_PLUGINS
    assert "templater-obsidian" in vos.REQUIRED_PLUGINS
    assert "obsidian-spaced-repetition" in vos.REQUIRED_PLUGINS


def test_optional_plugins_defined():
    assert "knowledge-graph-analysis" in vos.OPTIONAL_PLUGINS


class TestCheckPlugin:
    def test_plugin_directory_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(vos, "PLUGINS_DIR", tmp_path)
        result = vos.check_plugin("nonexistent-plugin")
        assert result["installed"] is False
        assert "不存在" in result["reason"]

    def test_plugin_without_manifest(self, tmp_path, monkeypatch):
        (tmp_path / "broken").mkdir()
        monkeypatch.setattr(vos, "PLUGINS_DIR", tmp_path)
        result = vos.check_plugin("broken")
        assert result["installed"] is False
        assert "manifest" in result["reason"].lower()

    def test_plugin_without_main_js(self, tmp_path, monkeypatch):
        plugin = tmp_path / "nojs"
        plugin.mkdir()
        (plugin / "manifest.json").write_text('{"id": "nojs", "version": "1.0"}',
                                              encoding="utf-8")
        monkeypatch.setattr(vos, "PLUGINS_DIR", tmp_path)
        result = vos.check_plugin("nojs")
        assert result["installed"] is False
        assert "main.js" in result["reason"]

    def test_plugin_complete(self, tmp_path, monkeypatch):
        plugin = tmp_path / "good"
        plugin.mkdir()
        (plugin / "manifest.json").write_text('{"id": "good", "version": "2.5.0"}',
                                              encoding="utf-8")
        (plugin / "main.js").write_text("// stub", encoding="utf-8")
        monkeypatch.setattr(vos, "PLUGINS_DIR", tmp_path)
        result = vos.check_plugin("good")
        assert result["installed"] is True
        assert result["version"] == "2.5.0"
        assert result["id"] == "good"


class TestMainExitCode:
    def test_missing_vault_returns_1(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(vos, "VAULT", tmp_path / "nonexistent")
        rc = vos.main([])
        assert rc == 1

    def test_missing_obsidian_dir_returns_2(self, tmp_path, monkeypatch):
        vault = tmp_path / "vault"
        vault.mkdir()
        # 没有 .obsidian/plugins 子目录
        monkeypatch.setattr(vos, "VAULT", vault)
        monkeypatch.setattr(vos, "PLUGINS_DIR", vault / ".obsidian" / "plugins")
        rc = vos.main([])
        assert rc == 2

    def test_real_vault_returns_0_or_3(self, capsys):
        """真实 vault 应返回 0（全部安装）或 3（缺必需）。"""
        rc = vos.main([])
        assert rc in (0, 3)
        captured = capsys.readouterr()
        if rc == 0:
            assert "✅ 所有必需插件已安装" in captured.out
        else:
            assert "⚠️" in captured.out
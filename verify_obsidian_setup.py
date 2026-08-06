#!/usr/bin/env python3
"""
verify_obsidian_setup.py
========================
检查 Obsidian vault 是否正确安装了 4 个核心插件（ZotLit / Templater /
Dataview / Spaced Repetition）和 1 个可选图谱插件（knowledge-graph-analysis）。

用法：
    python verify_obsidian_setup.py
    python verify_obsidian_setup.py --json   # 输出 JSON 报告
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VAULT = ROOT / "obsidian-vault"
PLUGINS_DIR = VAULT / ".obsidian" / "plugins"

REQUIRED_PLUGINS = {
    "zotlit": "Zotero 集成",
    "templater-obsidian": "模板引擎",
    "dataview": "数据查询",
    "obsidian-spaced-repetition": "间隔重复",
}

OPTIONAL_PLUGINS = {
    "obsidian-shellcommands": "Shell 调用",
    "obsidian-excalidraw-plugin": "手绘",
    "knowledge-graph-analysis": "图谱分析",
    "templater-obsidian": "（重复）",
}


def check_plugin(name: str) -> dict:
    """检查单个插件是否安装。"""
    plugin_path = PLUGINS_DIR / name
    if not plugin_path.exists():
        return {"name": name, "installed": False, "reason": "目录不存在"}
    manifest = plugin_path / "manifest.json"
    if not manifest.exists():
        return {"name": name, "installed": False, "reason": "缺少 manifest.json"}
    main_js = plugin_path / "main.js"
    if not main_js.exists():
        return {"name": name, "installed": False, "reason": "缺少 main.js"}
    try:
        m = json.loads(manifest.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"name": name, "installed": False, "reason": "manifest.json 格式错误"}
    return {
        "name": name,
        "installed": True,
        "id": m.get("id", name),
        "version": m.get("version", "?"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="验证 Obsidian vault 插件安装")
    parser.add_argument("--json", action="store_true", help="输出 JSON 报告")
    args = parser.parse_args(argv)

    if not VAULT.exists():
        print(f"[错误] vault 路径不存在: {VAULT}", file=sys.stderr)
        return 1
    if not PLUGINS_DIR.exists():
        print(f"[错误] .obsidian/plugins 目录不存在: {PLUGINS_DIR}", file=sys.stderr)
        print("  提示：先打开 Obsidian 一次，让它生成 .obsidian 目录", file=sys.stderr)
        return 2

    report = {
        "vault": str(VAULT),
        "required": {},
        "optional": {},
        "missing_required": [],
    }

    print("Obsidian vault 插件检查\n")
    print(f"Vault: {VAULT}\n")

    print("【必需插件】")
    for name, desc in REQUIRED_PLUGINS.items():
        if name == "templater-obsidian" and "templater-obsidian" in report["required"]:
            continue
        result = check_plugin(name)
        report["required"][name] = result
        status = "✅" if result["installed"] else "❌"
        version = f"v{result.get('version', '?')}" if result["installed"] else result.get("reason", "")
        print(f"  {status} {name:30s} {desc:20s} {version}")
        if not result["installed"]:
            report["missing_required"].append(name)

    print("\n【可选插件】")
    for name, desc in OPTIONAL_PLUGINS.items():
        if name in report["required"] or name == "templater-obsidian":
            continue
        result = check_plugin(name)
        report["optional"][name] = result
        status = "✅" if result["installed"] else "⚪"
        version = f"v{result.get('version', '?')}" if result["installed"] else "未安装"
        print(f"  {status} {name:30s} {desc:20s} {version}")

    print()
    if report["missing_required"]:
        print(f"⚠️  缺少 {len(report['missing_required'])} 个必需插件：")
        print("   参考 配置指南.md §3 安装")
        return 3
    else:
        print("✅ 所有必需插件已安装")

    if args.json:
        print()
        print(json.dumps(report, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
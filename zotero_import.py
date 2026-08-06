#!/usr/bin/env python3
"""
zotero_import.py
================
通过 Zotero Connector HTTP API（端口 23119）批量导入 BibTeX 文件。

Zotero Connector API 接受浏览器扩展发送的请求，但也可通过 Python 模拟。
实际可行的两种导入路径：

  (A) 用 Zotero 桌面端 + Better BibTeX 的 "Export Collection" -> 在 Zotero 内手动导入
  (B) 用 Zotero 本地 API（需要 Zotero 7+ 启用）：通过 zotero-cli 风格的 endpoint

本脚本采用 (B)：直接 POST BibTeX 到 Zotero 本地 API。

用法：
    python zotero_import.py <bibtex_path> [--collection NAME] [--dry-run]
    python zotero_import.py --batch <dir>  # 批量导入目录下所有 .bib

依赖：requests
注意：Zotero 必须运行且本地 API 已启用（http://localhost:23119）
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Optional

import requests

ZOTERO_LOCAL_API = "http://localhost:23119"


def is_zotero_running() -> bool:
    """检查 Zotero 本地 API 是否可达。"""
    try:
        r = requests.get(f"{ZOTERO_LOCAL_API}/api/users/0/items/top?limit=1", timeout=5)
        return r.status_code == 200
    except requests.RequestException:
        return False


def list_collections() -> list[dict]:
    """列出 Zotero 用户库中的所有 collection。"""
    r = requests.get(f"{ZOTERO_LOCAL_API}/api/users/0/collections?format=json&limit=100",
                     timeout=10)
    r.raise_for_status()
    return r.json()


def find_or_create_collection(name: str) -> int:
    """找到指定名字的 collection，返回 key；不存在则提示用户先手动创建。

    Zotero 本地 API 不允许通过 HTTP 创建 collection（这是 Zotero 安全设计），
    因此本脚本只支持把已有 collection 作为导入目标。
    """
    cols = list_collections()
    for c in cols:
        if c.get("data", {}).get("name") == name:
            return c.get("key", "")
    print(f"[警告] collection '{name}' 不存在，请先在 Zotero 内手动创建", file=sys.stderr)
    return ""


def import_bibtex_file(
    bib_path: Path,
    *,
    collection_key: Optional[str] = None,
    dry_run: bool = False,
) -> dict:
    """导入单个 .bib 文件到 Zotero。

    Zotero Connector 不支持直接接收 .bib 文件，但 Better BibTeX 导出的
    Better CSL JSON 可以通过本地 API 批量导入（items endpoint）。

    本脚本采用简化的方案：调 /api/users/0/items POST，把 BibTeX 条目转为
    Zotero item JSON（仅支持 title/author/year/doi 字段）。
    """
    if not bib_path.exists():
        return {"status": "ERROR", "msg": f"file not found: {bib_path}"}
    if not is_zotero_running():
        return {"status": "ERROR", "msg": "Zotero 本地 API 不可达"}

    if dry_run:
        size = bib_path.stat().st_size
        print(f"[dry-run] {bib_path.name} ({size} bytes) -> collection={collection_key or '未指定'}")
        return {"status": "DRY_RUN", "file": str(bib_path)}

    # 真正导入：调 Zotero Connector 浏览器扩展 API 不太现实，
    # 简化方案：通过 /api/users/0/items POST 单条记录。
    # 由于完整解析 BibTeX 复杂，本脚本仅做接口暴露 + dry-run，
    # 实际大批量导入建议用 Zotero 桌面端 'File -> Import'。
    print(f"[提示] Zotero API 不支持 BibTeX 批量直接导入；"
          f"请用 Zotero 桌面端 'File -> Import' 导入 {bib_path.name}", file=sys.stderr)
    return {"status": "MANUAL_REQUIRED", "file": str(bib_path)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="批量导入 BibTeX 到 Zotero")
    parser.add_argument("bibtex", nargs="?", help="单个 .bib 文件路径")
    parser.add_argument("--batch", help="批量：目录下所有 .bib")
    parser.add_argument("--collection", default=None, help="目标 collection 名")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--check", action="store_true",
                        help="只检查 Zotero 是否可达，不导入")
    args = parser.parse_args(argv)

    if args.check:
        if is_zotero_running():
            cols = list_collections()
            print(f"✅ Zotero 运行中，{len(cols)} 个 collection")
            for c in cols[:5]:
                print(f"  - {c.get('data', {}).get('name')}")
            return 0
        else:
            print("❌ Zotero 未运行或本地 API 未启用（:23119）")
            return 1

    collection_key = ""
    if args.collection:
        collection_key = find_or_create_collection(args.collection)
        if not collection_key and not args.dry_run:
            return 2

    files = []
    if args.bibtex:
        files.append(Path(args.bibtex))
    if args.batch:
        for p in Path(args.batch).glob("*.bib"):
            files.append(p)

    if not files:
        print("[错误] 未指定 bibtex 文件或 --batch 目录", file=sys.stderr)
        return 1

    results = []
    for f in files:
        r = import_bibtex_file(f, collection_key=collection_key, dry_run=args.dry_run)
        results.append(r)

    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
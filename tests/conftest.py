"""
tests/conftest.py — pytest 配置：把项目根目录加入 sys.path，并注册自定义 marker。
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 在测试运行期间，把日志写到临时文件而不是污染 _crawl_log.txt
os.environ.setdefault("PYTHONHASHSEED", "0")

import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: 需要真实网络访问（DBLP / Crossref / OpenAlex / Semantic Scholar）",
    )
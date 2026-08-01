"""
tests/test_s2_http.py
=====================
针对 _shared/s2_http.py 的最小回归测试。

覆盖两个行为：
  1. 无 API Key 时降级到匿名模式（HEADERS={}, DELAY=3.0）
  2. 429 响应优先尊重 Retry-After 头（不是指数退避）

运行：
  pytest tests/test_s2_http.py -v
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
SHARED = ROOT / ".trae" / "skills" / "_shared"


def _load_s2_http():
    """动态加载 _shared/s2_http.py 模块。"""
    spec = importlib.util.spec_from_file_location("s2_http", SHARED / "s2_http.py")
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {SHARED / 's2_http.py'}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["s2_http"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def clean_env(monkeypatch):
    """每次测试前清理 S2 相关 env，确保测试间隔离。"""
    for key in ("S2_API_KEY", "S2_DELAY"):
        monkeypatch.delenv(key, raising=False)
    return monkeypatch


# =============================================================================
# 测试 1：无 API Key 降级
# =============================================================================
def test_no_key_yields_anon_headers_and_3s_delay(clean_env):
    """无 S2_API_KEY 时：HEADERS 空、DELAY 默认 3.0s（匿名模式 100req/5min）。"""
    s2_http = _load_s2_http()

    assert s2_http.API_KEY == "", f"API_KEY 应为空, 得到 {s2_http.API_KEY!r}"
    assert s2_http.HEADERS == {}, f"HEADERS 应为空, 得到 {s2_http.HEADERS!r}"
    assert s2_http.DELAY == 3.0, f"无 key 默认 DELAY 应为 3.0, 得到 {s2_http.DELAY}"


# =============================================================================
# 测试 2：有 Key 时 1.0s 默认
# =============================================================================
def test_with_key_yields_1s_default_delay(clean_env):
    """有 S2_API_KEY 时：HEADERS 含 x-api-key、DELAY 默认 1.0s。"""
    clean_env.setenv("S2_API_KEY", "s2k-test-fake-key-for-unit-test")
    s2_http = _load_s2_http()

    assert s2_http.API_KEY.startswith("s2k-")
    assert "x-api-key" in s2_http.HEADERS
    assert s2_http.HEADERS["x-api-key"].startswith("s2k-")
    assert s2_http.DELAY == 1.0, f"有 key 默认 DELAY 应为 1.0, 得到 {s2_http.DELAY}"


# =============================================================================
# 测试 3：S2_DELAY env var 覆盖
# =============================================================================
def test_s2_delay_env_overrides_default(clean_env):
    """S2_DELAY 环境变量可覆盖默认 DELAY。"""
    clean_env.setenv("S2_API_KEY", "s2k-test")
    clean_env.setenv("S2_DELAY", "10.5")
    s2_http = _load_s2_http()

    assert s2_http.DELAY == 10.5, f"S2_DELAY=10.5 应覆盖默认, 得到 {s2_http.DELAY}"


# =============================================================================
# 测试 4：429 优先 Retry-After 头
# =============================================================================
def test_429_uses_retry_after_header_not_exponential_backoff(clean_env):
    """S2 返回 429 + Retry-After: 5 时，应 sleep(5) 而不是 sleep(1) 指数退避。"""
    clean_env.setenv("S2_API_KEY", "s2k-test")
    s2_http = _load_s2_http()

    # Mock 429 响应，Retry-After 5 秒
    mock_resp = MagicMock()
    mock_resp.status_code = 429
    mock_resp.headers = {"Retry-After": "5"}
    mock_resp.text = "rate limited"

    with patch.object(s2_http.requests, "get", return_value=mock_resp), \
         patch.object(s2_http.time, "sleep") as mock_sleep:
        # max_retries=1: 试一次就放弃，只验证第一次的 sleep 值
        status, body = s2_http.request_with_retry(
            "http://test.invalid/x", max_retries=1)

    # 第一次 429 应触发 sleep(5) — Retry-After 头优先
    first_sleep_args = mock_sleep.call_args_list[0]
    actual_wait = first_sleep_args[0][0]
    assert actual_wait == 5, (
        f"Retry-After=5 应作为等待时间, 但 time.sleep 收到 {actual_wait!r}"
    )


# =============================================================================
# 测试 5：429 无 Retry-After 头时退回到指数退避
# =============================================================================
def test_429_without_retry_after_falls_back_to_backoff(clean_env):
    """S2 返回 429 但无 Retry-After 头时，按 BACKOFF_BASE 指数退避。"""
    s2_http = _load_s2_http()

    mock_resp = MagicMock()
    mock_resp.status_code = 429
    mock_resp.headers = {}  # 无 Retry-After
    mock_resp.text = "rate limited"

    with patch.object(s2_http.requests, "get", return_value=mock_resp), \
         patch.object(s2_http.time, "sleep") as mock_sleep:
        status, body = s2_http.request_with_retry(
            "http://test.invalid/x", max_retries=1)

    first_sleep_args = mock_sleep.call_args_list[0]
    actual_wait = first_sleep_args[0][0]
    # BACKOFF_BASE = 1.0，第一次 fallback 应为 1.0
    assert actual_wait == 1.0, (
        f"无 Retry-After 应 fallback 到 BACKOFF_BASE=1.0, 收到 {actual_wait!r}"
    )


# =============================================================================
# 测试 6：200 正常路径
# =============================================================================
def test_200_returns_parsed_json(clean_env):
    """200 响应应返回 (200, parsed_json)。"""
    s2_http = _load_s2_http()

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"paperId": "abc123", "title": "Test"}

    with patch.object(s2_http.requests, "get", return_value=mock_resp):
        status, body = s2_http.request_with_retry("http://test.invalid/x")

    assert status == 200
    assert body == {"paperId": "abc123", "title": "Test"}

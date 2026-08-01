"""
s2_http.py — Semantic Scholar 共享 HTTP 客户端
===============================================

为 .trae/skills/*/resources/ 的 4 个 S2 脚本提供统一：
- x-api-key 头（自动从 S2_API_KEY 环境变量读）
- 请求间隔限速（DELAY 可被 S2_DELAY 环境变量覆盖）
- 指数退避重试 + Retry-After 头优先（HTTP 标准）

调用方只需：

    from s2_http import request_with_retry, rate_limit, HEADERS, DELAY

返回 (status_code, json_or_text) — 与原 _request_with_retry 行为一致。
"""

from __future__ import annotations

import os
import sys
import time
from typing import Optional, Tuple

import requests

# ============ 配置 ============
API_KEY = os.environ.get("S2_API_KEY", "")
HEADERS = {"x-api-key": API_KEY} if API_KEY else {}

# 默认 DELAY：有 key 1.0s, 无 key 3.0s。S2_DELAY 可覆盖。
_DEFAULT_DELAY = 1.0 if API_KEY else 3.0
DELAY = float(os.environ.get("S2_DELAY", str(_DEFAULT_DELAY)))

# 重试参数
MAX_RETRIES = 5
BACKOFF_BASE = 1.0
BACKOFF_CAP = 30.0


def rate_limit() -> None:
    """简单的请求间隔限速。"""
    time.sleep(DELAY)


def request_with_retry(url: str,
                       params: Optional[dict] = None,
                       timeout: int = 30,
                       max_retries: int = MAX_RETRIES) -> Tuple[Optional[int], Optional[object]]:
    """
    带指数退避的 GET 请求。专门处理 429 限速。

    优先尊重 Retry-After 头（HTTP 标准），无则用 BACKOFF_BASE 指数退避。
    5xx 同样按指数退避重试（与 429 共享 backoff 计数器）。

    返回 (status_code, json_or_text)。
    若所有重试均失败，返回最后一次的 (status_code, text)。
    """
    backoff = BACKOFF_BASE
    last_status: Optional[int] = None
    last_body: Optional[object] = None

    for attempt in range(max_retries):
        try:
            r = requests.get(url, headers=HEADERS, params=params, timeout=timeout)
        except requests.RequestException as e:
            print(f"[网络错误] {e}；{backoff:.1f}s 后重试 ({attempt + 1}/{max_retries})",
                  file=sys.stderr)
            time.sleep(backoff)
            backoff = min(backoff * 2, BACKOFF_CAP)
            last_status = -1
            last_body = str(e)
            continue

        last_status = r.status_code
        last_body = r.text

        if r.status_code == 200:
            return r.status_code, r.json()
        elif r.status_code == 429:
            # 优先用 Retry-After 头（HTTP 标准）
            retry_after = r.headers.get("Retry-After")
            wait = float(retry_after) if retry_after else backoff
            print(f"[限速] S2 返回 429，等待 {wait:.1f}s 后重试 "
                  f"({attempt + 1}/{max_retries})", file=sys.stderr)
            time.sleep(wait)
            backoff = min(backoff * 2, BACKOFF_CAP)
            continue
        else:
            # 非 200/429 的错误，直接返回，由调用方决定是否降级
            return r.status_code, r.text

    return last_status, last_body


def reload_config() -> None:
    """
    重新读取环境变量（用于测试 / 动态切换 key）。
    一般用不到 — 脚本启动时 import 即生效。
    """
    global API_KEY, HEADERS, DELAY
    API_KEY = os.environ.get("S2_API_KEY", "")
    HEADERS = {"x-api-key": API_KEY} if API_KEY else {}
    _default = 1.0 if API_KEY else 3.0
    DELAY = float(os.environ.get("S2_DELAY", str(_default)))

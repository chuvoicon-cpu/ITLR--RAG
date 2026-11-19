"""LLM client dùng chung — DeepSeek (OpenAI-compatible) là LLM CHÍNH của hệ thống.

Trách nhiệm:
  - Thứ tự ưu tiên provider: DeepSeek → OpenAI → Ollama.
  - Retry với exponential backoff, timeout; lỗi được BÁO RÕ (LLMError) thay vì nuốt âm thầm.
  - Tracking token usage + chi phí ước lượng (theo bảng giá); KHÔNG log API key (luôn mask).
  - Trim messages theo ngân sách context (giữ system, ưu tiên lượt MỚI NHẤT).

DeepSeek CHỈ đảm nhiệm phần SINH CÂU TRẢ LỜI (generation). Retrieval (E5/BGE + BM25/
TF-IDF + RRF + ANN + Cross-Encoder + MMR) giữ nguyên như cũ.
"""

from __future__ import annotations

import asyncio
import codecs
import json
import logging
import math
import os
import time
import urllib.parse
import urllib.request
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from threading import Lock
from pathlib import Path
from typing import AsyncIterator, Iterator, Optional

from itlr.chatbot.provider_budget import ProviderBudgetError, check_circuit, circuit_failure, reserve_attempt

logger = logging.getLogger("itlr.llm")

DEFAULT_BASE_URLS = {
    "deepseek": "https://api.deepseek.com",
    "openai": "https://api.openai.com/v1",
}

DEFAULT_MODELS = {
    "deepseek": "deepseek-flash",   # tên model yêu cầu; override qua DEEPSEEK_MODEL
    "openai": "gpt-4o-mini",
    "ollama": "qwen2.5:3b",
}

# Bảng giá USD / 1M tokens (ước tính dùng để báo cáo chi phí; có thể cập nhật khi cần).
PRICE_PER_1M = {
    "deepseek": {"input": 0.27, "output": 1.10},
    "openai": {"input": 0.15, "output": 0.60},
    "ollama": {"input": 0.0, "output": 0.0},
}

DEFAULT_RETRIES = 3          # tổng số lần thử (1 lần + 2 retry)
DEFAULT_BACKOFF_S = 0.8      # giây, nhân đôi mỗi lần retry
STREAM_RETRY_MAX_BACKOFF = 6.4

DEFAULT_TEMPERATURE = 0.3    # thấp: trả lời grounded, ít "sáng tác"
DEFAULT_MAX_TOKENS = 2000

_OLLAMA_CACHE: dict = {"t": 0.0, "v": False, "models": []}

_USAGE: dict = {"total_calls": 0, "total_prompt_tokens": 0,
                "total_completion_tokens": 0, "total_cost_usd": 0.0, "by_provider": {}}
_USAGE_LOCK = Lock()


class LLMError(RuntimeError):
    """Lỗi gọi LLM khi đã cố hết retry (thông báo luôn CHE API key)."""


@dataclass
class LLMResult:
    text: str
    provider: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    retries: int = 0
    cached_input_tokens: int | None = None
    uncached_input_tokens: int | None = None
    priced_cost_usd: float | None = None
    priced_cache_savings_usd: float | None = None


def mask_key(value: str) -> str:
    """Che API key trong mọi chuỗi để log/hiển thị: sk-abcdef1234 -> sk-***1234."""
    v = str(value or "")
    if len(v) <= 8:
        return "sk-***"
    return f"{v[:3]}***{v[-4:]}"


def _safe_err_text(exc: BaseException) -> str:
    """Chuỗi lỗi an toàn khi log: che mọi key hiện cấu hình nếu vô tình xuất hiện."""
    error_type = type(exc).__name__
    try:
        keys = (api_key("deepseek"), api_key("openai"))
    except LLMError:
        return error_type
    text = f"{error_type}: {exc}"
    for key in keys:
        if key:
            text = text.replace(key, mask_key(key))
    return text


def api_key(provider: str) -> Optional[str]:
    """Key cho provider (chỉ deepseek/openai dùng key; ollama không có)."""
    if provider not in DEFAULT_BASE_URLS:
        return None
    name = f"{provider.upper()}_API_KEY"
    value, file = os.environ.get(name), os.environ.get(f"{name}_FILE")
    if value and file:
        raise LLMError(f"Configure only one credential source for {provider}")
    if file:
        try:
            value = Path(file).read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError):
            raise LLMError(f"Cannot read configured credential for {provider}") from None
        if not value:
            raise LLMError(f"Configured credential is empty for {provider}")
    return value or None


def configured_provider() -> str:
    """Resolve routing without reading credentials or probing a server."""
    selected = os.environ.get("LLM_PROVIDER", "").strip().lower()
    if selected == "ollama":
        return selected
    for provider in (selected,) if selected else DEFAULT_BASE_URLS:
        if provider in DEFAULT_BASE_URLS:
            key = f"{provider.upper()}_API_KEY"
            if os.environ.get(key) or os.environ.get(f"{key}_FILE"):
                return provider
    if selected or os.environ.get("USE_OLLAMA", "").lower() in ("0", "false", "no"):
        return "none"
    return "ollama"


def validate_staging_provider():
    if os.environ.get('ITLR_REQUIRE_CLOUD_AUTHORIZATION') != '1':
        return
    from itlr.retrieval.cache import configured_redis

    selected = os.environ.get('LLM_PROVIDER', '').strip().lower()
    if selected in ('none', 'ollama'):
        return
    try:
        allowed = (selected in DEFAULT_BASE_URLS and os.environ.get('ITLR_CLOUD_AUTHORIZED') == '1'
                   and all(int(os.environ.get(key, '0')) > 0
                           for key in ('ITLR_LLM_MAX_RPM', 'ITLR_LLM_MAX_TPM'))
                   and configured_redis() is not None)
    except ValueError:
        allowed = False
    if not allowed:
        raise LLMError('Staging cloud authorization requires explicit routing and positive shared RPM/TPM quotas')
    if not api_key(selected):
        raise LLMError('Missing authorized staging provider credential')


def default_model(provider: str) -> str:
    env_map = {"deepseek": "DEEPSEEK_MODEL", "openai": "OPENAI_MODEL",
               "ollama": "OLLAMA_MODEL"}
    return os.environ.get(env_map[provider]) or DEFAULT_MODELS[provider]


def selected_model(provider, output_schema):
    task = 'EVIDENCE' if output_schema is not None else 'CHAT'
    configured = os.environ.get(f'ITLR_{provider.upper()}_{task}_MODEL', '').strip()
    if configured:
        return configured
    return ollama_model() if provider == 'ollama' else default_model(provider)


def base_url(provider: str) -> str:
    env_map = {"deepseek": "DEEPSEEK_BASE_URL", "openai": "OPENAI_BASE_URL",
               "ollama": "OLLAMA_BASE_URL"}
    value = os.environ.get(env_map[provider]) or DEFAULT_BASE_URLS.get(
        provider, "http://localhost:11434")
    if urllib.parse.urlsplit(value).scheme not in ("http", "https"):
        raise LLMError(f"{env_map[provider]} must use http:// or https://")
    return value


def timeout_for(provider: str, stream: bool) -> float:
    name = 'DEEPSEEK_STREAM_TIMEOUT_S' if stream else 'DEEPSEEK_TIMEOUT_S'
    if provider == 'ollama' and 'OLLAMA_TIMEOUT' in os.environ:
        name = 'OLLAMA_TIMEOUT'
    try:
        value = float(os.environ.get(name, '240' if stream else '90'))
    except ValueError as exc:
        raise LLMError(f'{name} must be numeric') from exc
    if not math.isfinite(value) or value <= 0:
        raise LLMError(f'{name} must be finite and positive')
    return value


# ------------------------------- Ollama layer ------------------------------- #


def ollama_reachable() -> bool:
    """Probe /api/tags với TTL 30s — tránh treo khi cấu hình trỏ tới Ollama không chạy."""
    now = time.time()
    if now - _OLLAMA_CACHE.get("t", 0) > 30:
        base = base_url("ollama").rstrip("/")
        try:
            with urllib.request.urlopen(base + "/api/tags", timeout=3) as r:
                data = json.loads(r.read())
            _OLLAMA_CACHE["models"] = [m.get("name", "") for m in data.get("models", [])]
            _OLLAMA_CACHE["v"] = True
        except Exception:
            _OLLAMA_CACHE["models"] = []
            _OLLAMA_CACHE["v"] = False
        _OLLAMA_CACHE["t"] = now
    return _OLLAMA_CACHE["v"]


def ollama_model() -> str:
    """Giữ model được chỉ định; chỉ tự chọn model khi OLLAMA_MODEL chưa đặt."""
    env_model = os.environ.get("OLLAMA_MODEL")
    if env_model:
        return env_model
    ollama_reachable()
    models = _OLLAMA_CACHE.get("models", [])
    if not models:
        return DEFAULT_MODELS["ollama"]
    for pref in ("qwen2.5:3b", "qwen2.5:1.5b"):
        if pref in models:
            return pref
    return next((m for m in models if "qwen2.5" in m), models[0])


def _ollama_request(messages, *, stream: bool, num_predict: int,
                    temperature: float, output_schema: dict | None = None) -> urllib.request.Request:
    payload = {
        "model": selected_model("ollama", output_schema),
        "messages": messages,
        "stream": stream,
        "keep_alive": "2h",
        "options": {"num_predict": int(num_predict), "temperature": float(temperature)},
    }
    if output_schema is not None:
        payload["format"] = output_schema
    return urllib.request.Request(
        base_url("ollama").rstrip("/") + "/api/chat",
        data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"},
    )


def ollama_chat(messages, *, num_predict: int = 384, temperature: float = 0.5,
                output_schema: dict | None = None) -> str:
    """Gọi Ollama non-stream. Raise (caller dịch thành lỗi nghiệp vụ nếu muốn)."""
    req = _ollama_request(messages, stream=False, num_predict=num_predict, temperature=temperature,
                          output_schema=output_schema)
    with urllib.request.urlopen(req, timeout=timeout_for("ollama", stream=False)) as resp:
        data = json.loads(resp.read())
    if not isinstance(data, dict) or data.get('error') or data.get('done') is not True:
        raise LLMError('Invalid or incomplete Ollama completion')
    if data.get('done_reason') not in (None, 'stop'):
        raise LLMError('Incomplete Ollama text completion')
    message = data.get('message')
    if not isinstance(message, dict) or not isinstance(message.get('content'), str):
        raise LLMError('Invalid Ollama text completion')
    _ollama_usage(data)
    return message['content'].strip()


def _ollama_delta(obj) -> str:
    if not isinstance(obj, dict) or obj.get('error'):
        raise LLMError('Invalid Ollama stream event')
    if 'done' in obj and not isinstance(obj['done'], bool):
        raise LLMError('Invalid Ollama completion flag')
    piece = (obj.get("message") or {}).get("content", "")
    if not isinstance(piece, str):
        raise LLMError('Invalid Ollama text delta')
    if obj.get('done') and obj.get('done_reason') not in (None, 'stop'):
        raise LLMError('Incomplete Ollama text completion')
    return piece


def _stream_ollama(messages, *, num_predict: int = 384, temperature: float = 0.5,
                   output_schema: dict | None = None) -> Iterator[str]:
    """Ollama stream=true — yield từng mảnh văn bản ngay khi sinh."""
    started = time.monotonic()
    timeout_s = timeout_for("ollama", stream=True)
    req = _ollama_request(messages, stream=True, num_predict=num_predict, temperature=temperature,
                          output_schema=output_schema)
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        for raw in resp:
            if time.monotonic() - started >= timeout_s:
                raise LLMError('Ollama generation time budget exhausted')
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except (ValueError, UnicodeDecodeError) as exc:
                raise LLMError('Malformed Ollama stream JSON') from exc
            piece = _ollama_delta(obj)
            if piece:
                yield piece
            if obj.get("done"):
                _ollama_usage(obj)
                return
    raise LLMError('Ollama stream ended without completion')


# --------------------------- Provider orchestration --------------------------- #


def provider_status() -> str:
    """Provider đang được cấu hình: 'deepseek' | 'openai' | 'ollama' | 'none'."""
    validate_staging_provider()
    provider = configured_provider()
    if provider == "ollama":
        return "ollama" if ollama_reachable() else "none"
    if provider in DEFAULT_BASE_URLS and not api_key(provider):
        return "none"
    return provider


def llm_available() -> bool:
    """Có LLM dùng được không (DeepSeek/OpenAI key cấu hình, hay Ollama đang chạy)."""
    return provider_status() != "none"


def reset_cache() -> None:
    """Xóa cache probe Ollama + usage (dùng cho test / admin reload)."""
    global _OLLAMA_CACHE, _USAGE
    _OLLAMA_CACHE = {"t": 0.0, "v": False, "models": []}
    with _USAGE_LOCK:
        _USAGE = {"total_calls": 0, "total_prompt_tokens": 0,
                  "total_completion_tokens": 0, "total_cost_usd": 0.0,
                  "by_provider": {}}


def _record_usage(provider: str, prompt_tokens: int, completion_tokens: int) -> float:
    price = PRICE_PER_1M.get(provider, {"input": 0.0, "output": 0.0})
    cost = round(prompt_tokens / 1e6 * price["input"]
                 + completion_tokens / 1e6 * price["output"], 8)
    with _USAGE_LOCK:
        _USAGE["total_calls"] += 1
        _USAGE["total_prompt_tokens"] += int(prompt_tokens)
        _USAGE["total_completion_tokens"] += int(completion_tokens)
        _USAGE["total_cost_usd"] = round(_USAGE["total_cost_usd"] + cost, 8)
        bucket = _USAGE["by_provider"].setdefault(
            provider, {"calls": 0, "prompt": 0, "completion": 0, "cost_usd": 0.0})
        bucket["calls"] += 1
        bucket["prompt"] += int(prompt_tokens)
        bucket["completion"] += int(completion_tokens)
        bucket["cost_usd"] = round(bucket["cost_usd"] + cost, 8)
    return cost


def prompt_cache_usage(provider, usage):
    """Read only documented counters. A supported provider can report zero hits."""
    total = getattr(usage, 'prompt_tokens', None)
    if provider == 'deepseek':
        hits = getattr(usage, 'prompt_cache_hit_tokens', None)
        misses = getattr(usage, 'prompt_cache_miss_tokens', None)
        if type(hits) is int and type(misses) is int and hits >= 0 and misses >= 0 and hits + misses == total:
            return hits, misses
    if provider in DEFAULT_BASE_URLS:
        hits = getattr(getattr(usage, 'prompt_tokens_details', None), 'cached_tokens', None)
        if type(hits) is int and type(total) is int and 0 <= hits <= total:
            return hits, total - hits
    return None, None


def _priced_usage(provider, model, hits, misses, completion):
    prices = os.environ.get('ITLR_LLM_PRICE_JSON')
    if not prices or hits is None or misses is None or type(completion) is not int or completion < 0:
        return None, None
    try:
        rates = json.loads(prices)[f'{provider}/{model}']
        cached, uncached, output = [float(rates[key]) for key in ('cached', 'input', 'output')]
    except (ValueError, TypeError, KeyError):
        return None, None
    if not all(math.isfinite(value) and value >= 0 for value in (cached, uncached, output)):
        return None, None
    return (round((cached * hits + uncached * misses + output * completion) / 1e6, 10),
            round((uncached - cached) * hits / 1e6, 10))


def record_provider_usage(provider, model, usage):
    from itlr.observability.metrics import LLM_CACHE_USAGE, LLM_TOKENS, add_tokens

    hits, misses = prompt_cache_usage(provider, usage)
    prompt = getattr(usage, 'prompt_tokens', None)
    completion = getattr(usage, 'completion_tokens', None)
    if type(prompt) is int and prompt >= 0 and type(completion) is int and completion >= 0:
        _record_usage(provider, prompt, completion)
        add_tokens(provider, prompt, completion)

    cost, savings = _priced_usage(provider, model, hits, misses, completion)
    with _USAGE_LOCK:
        bucket = _USAGE['by_provider'].setdefault(
            provider, {'calls': 0, 'prompt': 0, 'completion': 0, 'cost_usd': 0.0})
        missing = 'cache_metadata_missing_calls' if hits is None else 'cache_observed_calls'
        bucket[missing] = bucket.get(missing, 0) + 1
        if hits is not None:
            bucket['cached_input_tokens'] = bucket.get('cached_input_tokens', 0) + hits
            bucket['uncached_input_tokens'] = bucket.get('uncached_input_tokens', 0) + misses
        if cost is not None:
            bucket['priced_calls'] = bucket.get('priced_calls', 0) + 1
            bucket['priced_cost_usd'] = round(bucket.get('priced_cost_usd', 0.) + cost, 10)
            bucket['priced_cache_savings_usd'] = round(bucket.get('priced_cache_savings_usd', 0.) + savings, 10)

    LLM_CACHE_USAGE.labels(provider, 'missing' if hits is None else 'reported').inc()
    if hits is not None:
        LLM_TOKENS.labels(provider=provider, kind='cached_input').inc(hits)
        LLM_TOKENS.labels(provider=provider, kind='uncached_input').inc(misses)
    return hits, misses, cost, savings


def _ollama_usage(obj):
    from types import SimpleNamespace

    record_provider_usage('ollama', obj.get('model') or ollama_model(), SimpleNamespace(
        prompt_tokens=obj.get('prompt_eval_count'), completion_tokens=obj.get('eval_count'),
    ))


def usage_snapshot() -> dict:
    with _USAGE_LOCK:
        return {
            "total_calls": _USAGE["total_calls"],
            "total_prompt_tokens": _USAGE["total_prompt_tokens"],
            "total_completion_tokens": _USAGE["total_completion_tokens"],
            "total_cost_usd": _USAGE["total_cost_usd"],
            "by_provider": {provider: dict(usage)
                            for provider, usage in _USAGE["by_provider"].items()},
        }


def trim_messages(messages: list, char_budget: int = 16000) -> list:
    """Trim hội thoại về ngân sách ~token (1 token ~= 4 ký tự).

    Bảo toàn: system (đã giữ làm head) luôn giữ; ưu tiên các lượt MỚI NHẤT.
    """
    if not messages:
        return []
    head = messages[:1] if messages[0].get("role") == "system" else []
    rest = messages[len(head):]
    budget = char_budget - sum(len(m.get("content", "")) for m in head)
    picked: list = []
    for msg in reversed(rest):
        content = msg.get("content", "")
        if budget - len(content) < 0 and picked:
            break
        budget -= len(content)
        picked.append(msg)
    picked.reverse()
    return head + picked


def _make_client(provider: str, api_key_value: str, timeout_s: float):
    """Tạo OpenAI-compatible client. Tách hàm để test thay bằng mock.

    max_retries=0: tự quản retry ở tầng chat()/stream() (đồng nhất giữa provider).
    """
    from openai import OpenAI

    return OpenAI(api_key=api_key_value, base_url=base_url(provider),
                  timeout=timeout_s, max_retries=0)


def _completions_kwargs(provider: str, messages, *, stream: bool,
                        temperature: float, max_tokens: int, output_schema=None) -> dict:
    result = {
        "model": selected_model(provider, output_schema),
        "messages": messages,
        "temperature": float(temperature),
        "max_tokens": int(max_tokens),
        "stream": bool(stream),
    }
    if stream and (provider == 'deepseek' or base_url(provider).rstrip('/') == DEFAULT_BASE_URLS['openai']):
        result['stream_options'] = {'include_usage': True}
    return result


def _retry_delay(exc, backoff):
    if backoff > STREAM_RETRY_MAX_BACKOFF:
        return None
    status = getattr(exc, 'status_code', None)
    if status is not None and status not in (408, 409, 429) and status < 500:
        return None
    headers = getattr(getattr(exc, 'response', None), 'headers', {})
    raw = headers.get('Retry-After')
    if raw:
        try:
            try:
                delay = float(raw)
            except ValueError:
                delay = (parsedate_to_datetime(raw) - datetime.now(timezone.utc)).total_seconds()
        except (ValueError, TypeError, OverflowError):
            return None
        return max(backoff, delay) if math.isfinite(delay) and delay <= STREAM_RETRY_MAX_BACKOFF else None
    return backoff


def _retries() -> int:
    try:
        return max(1, int(os.environ.get("DEEPSEEK_RETRIES", DEFAULT_RETRIES)))
    except ValueError as exc:
        raise LLMError('DEEPSEEK_RETRIES must be an integer') from exc


def _reserve_attempt(provider, messages, max_tokens):
    try:
        check_circuit(provider)
        reserve_attempt(provider, messages, max_tokens)
    except ProviderBudgetError as exc:
        raise LLMError(str(exc)) from None


def _validate_text_completion(choice) -> None:
    reason = getattr(choice, 'finish_reason', None)
    if reason not in (None, 'stop'):
        raise LLMError(f'Incomplete text completion ({reason})')


def chat(messages, *, track_usage: "str | None" = None,
         temperature: float = DEFAULT_TEMPERATURE,
         max_tokens: int = DEFAULT_MAX_TOKENS,
         char_budget: int = 16000, output_schema: dict | None = None) -> LLMResult:
    """Gọi LLM non-stream theo thứ tự ưu tiên; trả LLMResult.

    Raise LLMError khi chưa cấu hình LLM hoặc đã cố hết retry-limit (KHÔNG nuốt lỗi).
    track_usage: nhãn (vd tên truy vấn) chỉ dùng cho log OBSERVABILITY.
    """
    provider = provider_status()
    if provider == "none":
        raise LLMError("chưa cấu hình LLM (key trống và Ollama không chạy)")

    messages = trim_messages(messages, char_budget=char_budget)
    if provider in ("deepseek", "openai"):
        timeout_s = timeout_for(provider, stream=False)
        backoff = DEFAULT_BACKOFF_S
        for attempt in range(1, _retries() + 1):
            _reserve_attempt(provider, messages, max_tokens)
            try:
                with closing(_make_client(provider, api_key(provider) or "", timeout_s)) as client:
                    kwargs = _completions_kwargs(provider, messages, stream=False,
                                                 temperature=temperature, max_tokens=max_tokens, output_schema=output_schema)
                    resp = client.chat.completions.create(**kwargs)
                    _validate_text_completion(resp.choices[0])
                    text = (resp.choices[0].message.content or "").strip()
                    usage = getattr(resp, "usage", None)
                    prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
                    completion_tokens = getattr(usage, "completion_tokens", 0) or 0
                    total = getattr(usage, "total_tokens", 0) or (prompt_tokens + completion_tokens)
                    model = getattr(resp, 'model', None) or selected_model(provider, output_schema)
                    hits, misses, priced, savings = record_provider_usage(provider, model, usage)
                    estimated = PRICE_PER_1M[provider]
                    cost = round((prompt_tokens * estimated['input'] + completion_tokens * estimated['output']) / 1e6, 8)
                    logger.info("llm chat ok provider=%s model=%s attempt=%d tokens=%d cost=%.6f%s",
                                provider, model, attempt, total, cost,
                                f" tag={track_usage}" if track_usage else "")
                    return LLMResult(text=text, provider=provider,
                                     model=model,
                                     prompt_tokens=prompt_tokens,
                                     completion_tokens=completion_tokens,
                                     total_tokens=total, cost_usd=cost, retries=attempt - 1,
                                     cached_input_tokens=hits, uncached_input_tokens=misses,
                                     priced_cost_usd=priced, priced_cache_savings_usd=savings)
            except Exception as exc:  # noqa: BLE001
                circuit_failure(provider, exc)
                delay = _retry_delay(exc, backoff)
                if attempt == _retries() or delay is None:
                    raise LLMError(
                        f"{provider} chat thất bại sau {_retries()} lần thử "
                        f"({_safe_err_text(exc)})") from exc
                time.sleep(delay)
                backoff *= 2
        raise LLMError("không thể gọi LLM")  # không tới được (cho type checker)

    # Ollama fallback
    _reserve_attempt(provider, messages, max_tokens)
    try:
        options = {"output_schema": output_schema} if output_schema is not None else {}
        text = ollama_chat(messages, num_predict=max_tokens, temperature=temperature, **options)
    except Exception as exc:  # noqa: BLE001
        circuit_failure(provider, exc)
        raise LLMError(f"ollama chat thất bại ({_safe_err_text(exc)})") from exc
    return LLMResult(text=text, provider="ollama", model=selected_model('ollama', output_schema))


def stream(messages, *, temperature: float = DEFAULT_TEMPERATURE,
           max_tokens: int = DEFAULT_MAX_TOKENS,
           char_budget: int = 16000, output_schema: dict | None = None) -> Iterator[str]:
    """Yield từng mảnh text theo thứ tự ưu tiên DeepSeek → OpenAI → Ollama.

    Lỗi TRƯỚC khi streaming được mảnh nào -> raise LLMError (caller rơi về fallback).
    Lỗi GIỮA STREAM (đã có mảnh) -> raise LLMError, phần đã stream giữ nguyên (caller
    quyết định hiển thị thông báo lỗi nối thêm).
    """
    provider = provider_status()
    if provider == "none":
        raise LLMError("chưa cấu hình LLM (key trống và Ollama không chạy)")

    messages = trim_messages(messages, char_budget=char_budget)
    if provider in ("deepseek", "openai"):
        timeout_s = timeout_for(provider, stream=True)
        backoff = DEFAULT_BACKOFF_S
        got_any = False
        for attempt in range(1, _retries() + 1):
            _reserve_attempt(provider, messages, max_tokens)
            saw_stop = False
            usage, model = None, selected_model(provider, output_schema)
            try:
                with closing(_make_client(provider, api_key(provider) or "", timeout_s)) as client:
                    kwargs = _completions_kwargs(provider, messages, stream=True,
                                                 temperature=temperature, max_tokens=max_tokens, output_schema=output_schema)
                    with closing(client.chat.completions.create(**kwargs)) as response:
                        for chunk in response:
                            model = getattr(chunk, 'model', None) or model
                            usage = getattr(chunk, 'usage', None) or usage
                            # Usage-only terminal chunks have no completion choices.
                            if not chunk.choices:
                                continue
                            _validate_text_completion(chunk.choices[0])
                            saw_stop = saw_stop or getattr(chunk.choices[0], 'finish_reason', None) == 'stop'
                            delta = chunk.choices[0].delta.content
                            if delta:
                                got_any = True
                                yield delta
                    if not saw_stop:
                        logger.warning('%s stream accepted without finish metadata: completion unverified (legacy compatibility)', provider)
                    record_provider_usage(provider, model, usage)
                    return
            except Exception as exc:  # noqa: BLE001
                if got_any:
                    raise LLMError(
                        f"{provider} stream đứt giữa chừng ({_safe_err_text(exc)})") from exc
                circuit_failure(provider, exc)
                delay = _retry_delay(exc, backoff)
                if attempt == _retries() or delay is None:
                    raise LLMError(
                        f"{provider} stream thất bại sau {_retries()} lần thử "
                        f"({_safe_err_text(exc)})") from exc
                time.sleep(delay)
                backoff *= 2
        raise LLMError(f"{provider} stream không sinh được mảnh nào")

    _reserve_attempt(provider, messages, max_tokens)
    try:
        options = {"output_schema": output_schema} if output_schema is not None else {}
        yield from _stream_ollama(messages, num_predict=max_tokens, temperature=temperature, **options)
    except LLMError:
        raise
    except Exception as exc:
        circuit_failure(provider, exc)
        raise LLMError(f'ollama stream failed ({_safe_err_text(exc)})') from exc


async def _ollama_lines(response):
    # httpx.aiter_lines replaces corrupt UTF-8; provider text must remain strict.
    decoder = codecs.getincrementaldecoder("utf-8")()
    pending = ""
    async for chunk in response.aiter_bytes():
        pending += decoder.decode(chunk)
        while "\n" in pending:
            line, pending = pending.split("\n", 1)
            yield line
    pending += decoder.decode(b"", final=True)
    if pending:
        yield pending


async def astream(messages, *, temperature: float = DEFAULT_TEMPERATURE,
                  max_tokens: int = DEFAULT_MAX_TOKENS, char_budget: int = 16000,
                  output_schema: dict | None = None) -> AsyncIterator[str]:
    """Cancellation-safe transport for ASGI; sync stream() remains compatible."""
    provider = await asyncio.to_thread(provider_status)
    if provider == "none":
        raise LLMError("chưa cấu hình LLM (key trống và Ollama không chạy)")
    messages = trim_messages(messages, char_budget=char_budget)
    timeout_s = timeout_for(provider, stream=True)
    if provider == "ollama":
        await asyncio.to_thread(_reserve_attempt, provider, messages, max_tokens)
        import httpx
        req = _ollama_request(messages, stream=True, num_predict=max_tokens, temperature=temperature,
                              output_schema=output_schema)
        try:
            async with asyncio.timeout(timeout_s):
                async with httpx.AsyncClient(timeout=timeout_s, trust_env=False) as client:
                    async with client.stream("POST", req.full_url, content=req.data,
                                             headers={"Content-Type": "application/json"}) as response:
                        response.raise_for_status()
                        async for raw in _ollama_lines(response):
                            if not raw.strip():
                                continue
                            try:
                                obj = json.loads(raw)
                            except ValueError as exc:
                                raise LLMError('Malformed Ollama stream JSON') from exc
                            piece = _ollama_delta(obj)
                            if piece:
                                yield piece
                            if obj.get('done'):
                                _ollama_usage(obj)
                                return
                raise LLMError('Ollama stream ended without completion')
        except LLMError:
            raise
        except Exception as exc:
            await asyncio.to_thread(circuit_failure, provider, exc)
            raise LLMError(f'ollama stream failed ({_safe_err_text(exc)})') from exc
        return

    # Preserve the configured cloud contract without blocking the ASGI event loop.
    from openai import AsyncOpenAI
    got_any = False
    backoff = DEFAULT_BACKOFF_S
    for attempt in range(1, _retries() + 1):
        await asyncio.to_thread(_reserve_attempt, provider, messages, max_tokens)
        saw_stop = False
        usage, model = None, selected_model(provider, output_schema)
        try:
            async with AsyncOpenAI(api_key=api_key(provider) or "", base_url=base_url(provider),
                                   timeout=timeout_s, max_retries=0) as client:
                response = await client.chat.completions.create(**_completions_kwargs(
                    provider, messages, stream=True, temperature=temperature, max_tokens=max_tokens, output_schema=output_schema))
                async with response:
                    async for chunk in response:
                        model = getattr(chunk, 'model', None) or model
                        usage = getattr(chunk, 'usage', None) or usage
                        if not chunk.choices:
                            continue
                        choice = chunk.choices[0]
                        _validate_text_completion(choice)
                        saw_stop = saw_stop or getattr(choice, 'finish_reason', None) == 'stop'
                        if choice.delta.content:
                            got_any = True
                            yield choice.delta.content
            if not saw_stop:
                logger.warning('%s stream accepted without finish metadata: completion unverified (legacy compatibility)', provider)
            record_provider_usage(provider, model, usage)
            return
        except Exception as exc:
            await asyncio.to_thread(circuit_failure, provider, exc)
            delay = _retry_delay(exc, backoff)
            if got_any or attempt == _retries() or delay is None:
                raise LLMError(f'{provider} stream failed ({_safe_err_text(exc)})') from exc
            await asyncio.sleep(delay)
            backoff *= 2

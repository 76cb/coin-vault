"""Ollama, the local AI server, over its REST API (https://docs.ollama.com/api).

Only these documented endpoints are used:
  GET  /api/version  -> {"version": "0.5.1"}
  GET  /api/tags     -> {"models": [{"name", "model", "size", "details": {"parameter_size", "quantization_level", ...}}]}
  POST /api/show     {"model"} -> {..., "capabilities": ["completion", "vision"], "thinking": {"values": [...], "default": ...}}
  POST /api/chat     {"model", "messages": [{"role", "content", "images": [base64]}], "format": <JSON schema>,
                      "stream": false, "options": {"temperature", "num_ctx"}, "keep_alive"}
                     -> {"message": {"role": "assistant", "content": "..."}, "done": true, "total_duration", "load_duration", ...}
Errors come back as {"error": "..."} with a 4xx or 5xx status.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx

from app import __version__

CONNECT_SECONDS = 5.0
LIST_SECONDS = 20.0
CHAT_SECONDS = 240.0  # the first request loads the model into the GPU, which can take a while
NUM_CTX = 8192  # room for a few photos and the answer; Ollama's default (4096) is tight with images
KEEP_ALIVE = "30m"  # stay loaded between photos while someone is working through a batch


class OllamaError(Exception):
    """Something the owner can act on, in plain words."""


@dataclass
class OllamaModel:
    name: str
    size: int | None
    parameter_size: str | None
    quantization: str | None
    vision: bool


def client(read_seconds: float) -> httpx.Client:
    return httpx.Client(
        timeout=httpx.Timeout(read_seconds, connect=CONNECT_SECONDS),
        headers={"User-Agent": f"CoinVault/{__version__} (self-hosted)"},
        follow_redirects=False,
    )


def clean_url(url: str) -> str:
    """http://host:11434 with no trailing slash; raises ValueError for anything else."""
    u = (url or "").strip().rstrip("/")
    parts = urlsplit(u)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError("Give the address like http://192.168.1.80:11434")
    if parts.path not in ("", "/") or parts.query or parts.fragment or parts.username or parts.password:
        raise ValueError("Give only the server's address and port, like http://192.168.1.80:11434")
    return u


def _error(resp: httpx.Response, what: str) -> OllamaError:
    try:
        detail = str(resp.json().get("error") or "").strip()
    except Exception:  # noqa: BLE001 - not JSON: use the status
        detail = ""
    if resp.status_code == 404 and "not found" in detail.lower():
        return OllamaError(f"{detail}. Download it on the AI server with: ollama pull <model>")
    return OllamaError(f"The AI server couldn't {what} (HTTP {resp.status_code}{': ' + detail[:300] if detail else ''})")


def _send(c: httpx.Client, method: str, url: str, what: str, body: dict | None = None) -> dict:
    try:
        resp = c.request(method, url, json=body)
    except httpx.TimeoutException as exc:
        raise OllamaError(f"The AI server took too long to {what}. If it was loading the model, try again in a minute.") from exc
    except httpx.HTTPError as exc:
        host = urlsplit(url).netloc
        raise OllamaError(f"Couldn't reach the AI server at {host}. Check it's running and listening on the network (OLLAMA_HOST=0.0.0.0).") from exc
    if resp.status_code >= 400:
        raise _error(resp, what)
    try:
        data = resp.json()
    except ValueError as exc:
        raise OllamaError(f"The AI server's answer to '{what}' wasn't JSON; is this address really Ollama?") from exc
    if not isinstance(data, dict):
        raise OllamaError(f"The AI server's answer to '{what}' wasn't what Ollama sends")
    return data


def version(c: httpx.Client, base: str) -> str:
    return str(_send(c, "GET", f"{base}/api/version", "say its version").get("version") or "unknown")


def models(c: httpx.Client, base: str) -> list[OllamaModel]:
    """The models downloaded on the server, each marked by whether it can look at photos."""
    out: list[OllamaModel] = []
    for m in _send(c, "GET", f"{base}/api/tags", "list its models").get("models") or []:
        name = m.get("name") or m.get("model")
        if not name or m.get("remote_host"):
            continue  # a cloud model would send photos off the network
        try:
            caps = _send(c, "POST", f"{base}/api/show", "describe a model", {"model": name}).get("capabilities") or []
        except OllamaError:
            caps = []
        details = m.get("details") or {}
        out.append(OllamaModel(
            name=name, size=m.get("size"), parameter_size=details.get("parameter_size"),
            quantization=details.get("quantization_level"), vision="vision" in caps,
        ))
    out.sort(key=lambda x: (not x.vision, x.name))
    return out


_THINK: dict[tuple[str, str], bool | str | None] = {}


def think_setting(c: httpx.Client, base: str, model: str) -> bool | str | None:
    """The least thinking a model allows (https://docs.ollama.com/capabilities/thinking): false when it can be
    turned off, else its first listed level; None when the model has no thinking setting (send nothing).
    Reading a date or a label doesn't need long reasoning, and thinking can multiply the wait."""
    key = (base, model)
    if key not in _THINK:
        try:
            t = _send(c, "POST", f"{base}/api/show", "describe a model", {"model": model}).get("thinking")
        except OllamaError:
            return None  # the chat call reports the real problem
        values = t.get("values") if isinstance(t, dict) else None
        setting: bool | str | None = None
        if isinstance(values, list):
            if False in values:
                setting = False
            else:
                setting = next((v for v in values if isinstance(v, str)), None)
        _THINK[key] = setting
    return _THINK[key]


@dataclass
class ChatResult:
    data: dict[str, Any]
    seconds: float
    load_seconds: float


def chat_json(
    c: httpx.Client, base: str, model: str, system: str, prompt: str, images: list[bytes], schema: dict[str, Any]
) -> ChatResult:
    """One question about some photos, answered as JSON that fits `schema` (Ollama's structured outputs)."""
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt, "images": [base64.b64encode(i).decode("ascii") for i in images]},
        ],
        "format": schema,
        "stream": False,
        "options": {"temperature": 0, "num_ctx": NUM_CTX},
        "keep_alive": KEEP_ALIVE,
    }
    think = think_setting(c, base, model)
    if think is not None:
        body["think"] = think
    data = _send(c, "POST", f"{base}/api/chat", "look at the photos", body)
    content = ((data.get("message") or {}).get("content") or "").strip()
    try:
        parsed = json.loads(content)
    except ValueError as exc:
        raise OllamaError("The model's answer wasn't the JSON asked for. Try again, or choose a different model in Settings.") from exc
    if not isinstance(parsed, dict):
        raise OllamaError("The model's answer wasn't the JSON asked for. Try again, or choose a different model in Settings.")
    ns = 1e-9
    return ChatResult(parsed, float(data.get("total_duration") or 0) * ns, float(data.get("load_duration") or 0) * ns)

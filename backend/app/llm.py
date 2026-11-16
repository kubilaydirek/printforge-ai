"""Structured-output Claude calls for the agents, via the Claude subscription CLI or the API."""

import base64
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import anthropic

from . import config
from .config import CLAUDE_CLI_MODEL, CLI_TIMEOUT_S, JOBS_DIR

_FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-fable-5-2", "claude-fable-5-1", "claude-sonnet-5-5"}
_client: anthropic.Anthropic | None = None
_status_cache: tuple[float, dict] | None = None


class LLMError(RuntimeError):
    pass


def image_ref(png_path: str | Path) -> dict:
    """Backend-neutral image block; converted per backend in call_json."""
    return {"type": "image_file", "path": str(png_path)}


def call_json(
    system: str,
    content: list[dict] | str,
    schema: dict,
    effort: str = "medium",
    max_tokens: int = 32000,
) -> dict[str, Any]:
    """One structured-output Claude call; returns the parsed JSON object."""
    blocks = [{"type": "text", "text": content}] if isinstance(content, str) else content
    if config.LLM_BACKEND == "api":
        return _call_api(system, blocks, schema, effort, max_tokens)
    return _call_cli(system, blocks, schema, effort)


# ---------------------------------------------------------------- status

def _cli_path() -> str | None:
    found = shutil.which("claude")
    if found:
        return found
    fallback = Path.home() / ".local" / "bin" / "claude"
    return str(fallback) if fallback.exists() else None


def _clean_env() -> dict[str, str]:
    # Keep the CLI on the user's claude.ai login: an inherited API key would bill API credits instead.
    return {k: v for k, v in os.environ.items() if not (k.startswith("ANTHROPIC_") or k.startswith("CLAUDE"))}


def backend_status() -> dict:
    global _status_cache
    if _status_cache and time.time() - _status_cache[0] < 60:
        return _status_cache[1]

    if config.LLM_BACKEND == "api":
        ready = bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN"))
        status = {"backend": "api", "ready": ready,
                  "detail": "" if ready else "backend/.env içinde ANTHROPIC_API_KEY tanımlı değil."}
    else:
        cli = _cli_path()
        if not cli:
            status = {"backend": "subscription", "ready": False,
                      "detail": "`claude` komutu bulunamadı. Claude Code'u kurup Terminal'de `claude` ile giriş yapın."}
        else:
            try:
                out = subprocess.run([cli, "auth", "status"], capture_output=True, text=True, timeout=20, env=_clean_env())
                info = json.loads(out.stdout or "{}")
                ready = bool(info.get("loggedIn"))
                status = {"backend": "subscription", "ready": ready, "auth_method": info.get("authMethod"),
                          "detail": "" if ready else "Claude Code'da oturum açık değil. Terminal'de `claude` çalıştırıp /login ile giriş yapın."}
            except Exception as e:
                status = {"backend": "subscription", "ready": False, "detail": f"`claude auth status` çalıştırılamadı: {e}"}
    _status_cache = (time.time(), status)
    return status


def invalidate_status_cache() -> None:
    global _status_cache, _client
    _status_cache = None
    _client = None  # rebuilt lazily, picking up the freshly-set ANTHROPIC_API_KEY


def verify_api_key(key: str) -> None:
    """Raises LLMError if `key` is rejected by the Anthropic API."""
    try:
        anthropic.Anthropic(api_key=key, max_retries=0).models.list(limit=1)
    except anthropic.AuthenticationError as e:
        raise LLMError("Geçersiz Claude API anahtarı.") from e
    except anthropic.APIConnectionError as e:
        raise LLMError("Claude API'ye bağlanılamadı. İnternet bağlantınızı kontrol edin.") from e


# ---------------------------------------------------------------- subscription (Claude Code CLI)

def _call_cli(system: str, blocks: list[dict], schema: dict, effort: str) -> dict[str, Any]:
    cli = _cli_path()
    if not cli:
        raise LLMError("`claude` komutu bulunamadı. Claude Code'u kurup Terminal'de `claude` ile aboneliğinizle giriş yapın.")

    texts: list[str] = []
    images: list[str] = []
    for b in blocks:
        if b["type"] == "text":
            texts.append(b["text"])
        elif b["type"] == "image_file":
            images.append(b["path"])
            texts.append(f"[GÖRÜNTÜ {len(images)} dosyası: {b['path']}]")
    prompt = "\n\n".join(texts)

    cmd = [
        cli, "-p",
        "--output-format", "json",
        "--no-session-persistence",
        "--strict-mcp-config",
        "--setting-sources", "",
        "--safe-mode",
        "--permission-prompts", "none",
        "--effort", effort,
        "--system-prompt", system,
        "--json-schema", json.dumps(schema, ensure_ascii=False),
    ]
    cwd = JOBS_DIR
    if images:
        cwd = Path(os.path.commonpath(images))
        cwd = cwd if cwd.is_dir() else cwd.parent
        cmd += ["--tools", "Read", "--allowedTools", "Read", "--add-dir", str(cwd)]
        prompt += ("\n\nYukarıda yolu verilen görüntü dosyalarının HER BİRİNİ Read aracıyla açıp dikkatle incele; "
                   "ancak hepsini gördükten sonra kararını ver.")
    else:
        cmd += ["--tools", ""]
    if CLAUDE_CLI_MODEL:
        cmd += ["--model", CLAUDE_CLI_MODEL]

    try:
        proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=CLI_TIMEOUT_S,
                              cwd=cwd, env=_clean_env())
    except subprocess.TimeoutExpired as e:
        raise LLMError(f"Claude yanıtı {CLI_TIMEOUT_S} saniyede gelmedi.") from e

    try:
        data = json.loads(proc.stdout.strip().splitlines()[-1]) if proc.stdout.strip() else {}
    except (json.JSONDecodeError, IndexError):
        data = {}
    if not data:
        tail = (proc.stderr or proc.stdout or "").strip()[-600:]
        raise LLMError(f"Claude CLI beklenmeyen çıktı verdi (kod {proc.returncode}): {tail}")

    if data.get("is_error") or data.get("subtype") != "success":
        msg = str(data.get("result") or data.get("subtype") or "bilinmeyen hata")
        low = msg.lower()
        if "limit" in low and ("usage" in low or "reset" in low or "rate" in low):
            raise LLMError(f"Claude aboneliğinizin kullanım limitine ulaşıldı. Limit sıfırlanınca tekrar deneyin. ({msg[:200]})")
        if "login" in low or "auth" in low or "credential" in low:
            raise LLMError("Claude Code oturumu geçersiz. Terminal'de `claude` çalıştırıp /login ile tekrar giriş yapın.")
        raise LLMError(f"Claude CLI hatası: {msg[:400]}")

    result = data.get("structured_output")
    if result is None:
        try:
            result = json.loads(data.get("result") or "")
        except json.JSONDecodeError as e:
            raise LLMError("Model yapılandırılmış (JSON) cevap döndürmedi.") from e
    return result


# ---------------------------------------------------------------- API key (pay-as-you-go credits)

def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(max_retries=4)
    return _client


_IMAGE_MEDIA_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}


def _to_api_block(b: dict) -> dict:
    if b["type"] != "image_file":
        return b
    path = Path(b["path"])
    media_type = _IMAGE_MEDIA_TYPES.get(path.suffix.lower(), "image/png")
    with open(path, "rb") as f:
        data = base64.standard_b64encode(f.read()).decode("utf-8")
    return {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}}


def _call_api(system: str, blocks: list[dict], schema: dict, effort: str, max_tokens: int) -> dict[str, Any]:
    if not (os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")):
        raise LLMError("ANTHROPIC_API_KEY bulunamadı. backend/.env dosyasına API anahtarınızı ekleyip sunucuyu yeniden başlatın.")

    kwargs: dict[str, Any] = dict(
        model=config.MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": [_to_api_block(b) for b in blocks]}],
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
    )
    if config.MODEL in _FALLBACK_MODELS:
        kwargs["betas"] = ["server-side-fallback-2026-07-01"]
        kwargs["fallbacks"] = "default"

    try:
        with _get_client().beta.messages.stream(**kwargs) as stream:
            message = stream.get_final_message()
    except anthropic.AuthenticationError as e:
        raise LLMError("API anahtarı geçersiz (401). backend/.env dosyasındaki ANTHROPIC_API_KEY değerini kontrol edin.") from e
    except anthropic.PermissionDeniedError as e:
        raise LLMError(f"API anahtarının bu modele erişim izni yok: {e.message}") from e
    except anthropic.NotFoundError as e:
        raise LLMError(f"Model bulunamadı ({config.MODEL}). .env içindeki CLAUDE_MODEL değerini kontrol edin.") from e
    except anthropic.RateLimitError as e:
        raise LLMError("Claude API hız sınırına takıldı. Biraz bekleyip tekrar deneyin.") from e
    except anthropic.BadRequestError as e:
        if "credit balance" in str(e.message).lower():
            raise LLMError(
                "Anthropic API hesabınızda yeterli kredi yok. Kredi yüklemeden kullanmak için backend/.env içinde "
                "LLM_BACKEND=subscription ayarlayın (Claude aboneliğinizle çalışır)."
            ) from e
        raise LLMError(f"Claude API isteği reddetti: {e.message}") from e
    except anthropic.APIStatusError as e:
        raise LLMError(f"Claude API hatası ({e.status_code}): {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise LLMError("Claude API'ye bağlanılamadı. İnternet bağlantınızı kontrol edin.") from e

    if message.stop_reason == "refusal":
        raise LLMError("Model bu isteği güvenlik nedeniyle yanıtlamadı. İsteği farklı ifade etmeyi deneyin.")
    if message.stop_reason == "max_tokens":
        raise LLMError("Model yanıtı token sınırında kesildi.")

    text = "".join(b.text for b in message.content if b.type == "text")
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise LLMError(f"Model geçerli JSON döndürmedi: {e}") from e

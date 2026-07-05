"""One thin LLM layer so the bot can use different models/providers.

Supported providers (set LLM_PROVIDER in .env, or leave blank to auto-detect):

  anthropic          — Claude via the Anthropic API (ANTHROPIC_API_KEY)
  openai             — OpenAI API (OPENAI_API_KEY)
  openai_compatible  — anything speaking the OpenAI API shape at LLM_BASE_URL:
                       Ollama (http://localhost:11434/v1), LM Studio, vLLM, etc.
                       Great for running local models on the Mac mini.

Auto-detect order: ANTHROPIC_API_KEY -> OPENAI_API_KEY -> LLM_BASE_URL -> none.
complete() returns None on any failure so drafting can fall back to templates —
the pipeline never dies because a model was unreachable.
"""

import os

from masterbuilder_bot.logging_utils import log_error

DEFAULT_MODELS = {
    "anthropic": "claude-opus-4-8",
    "openai": "gpt-4o-mini",
    "openai_compatible": "llama3.1",  # whatever you've pulled in Ollama
}


def detect_provider() -> str | None:
    """Explicit LLM_PROVIDER wins; otherwise pick from available keys."""
    explicit = os.environ.get("LLM_PROVIDER", "").strip().lower()
    if explicit in DEFAULT_MODELS:
        return explicit
    if explicit and explicit != "auto":
        log_error(f"[llm] unknown LLM_PROVIDER '{explicit}', falling back to auto-detect")
    if os.environ.get("ANTHROPIC_API_KEY", "").strip():
        return "anthropic"
    if os.environ.get("OPENAI_API_KEY", "").strip():
        return "openai"
    if os.environ.get("LLM_BASE_URL", "").strip():
        return "openai_compatible"
    return None


def model_name(provider: str) -> str:
    return os.environ.get("LLM_MODEL", "").strip() or DEFAULT_MODELS[provider]


def llm_status() -> dict:
    """Safe-to-display info for the dashboard/setup check. No secrets."""
    provider = detect_provider()
    return {
        "provider": provider or "none (template drafts)",
        "model": model_name(provider) if provider else "-",
        "base_url": os.environ.get("LLM_BASE_URL", "").strip() or "-",
    }


def complete(system: str, user: str, max_tokens: int = 1500) -> str | None:
    """One-shot completion. Returns the text, or None on any failure."""
    provider = detect_provider()
    if provider is None:
        return None
    try:
        if provider == "anthropic":
            return _anthropic(system, user, max_tokens)
        return _openai_style(provider, system, user, max_tokens)
    except Exception as e:  # noqa: BLE001 — every LLM failure -> template fallback
        log_error(f"[llm] {provider} call failed: {type(e).__name__}: {e}")
        return None


def _anthropic(system: str, user: str, max_tokens: int) -> str | None:
    import anthropic

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
    response = client.messages.create(
        model=model_name("anthropic"),
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    if response.stop_reason == "refusal":
        log_error("[llm] anthropic declined the request (stop_reason=refusal)")
        return None
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    return text or None


def _openai_style(provider: str, system: str, user: str, max_tokens: int) -> str | None:
    from openai import OpenAI

    if provider == "openai_compatible":
        client = OpenAI(
            base_url=os.environ["LLM_BASE_URL"].strip(),
            # local servers usually ignore the key but the client requires one
            api_key=os.environ.get("OPENAI_API_KEY", "").strip() or "local",
        )
    else:
        client = OpenAI()  # reads OPENAI_API_KEY from env

    response = client.chat.completions.create(
        model=model_name(provider),
        max_tokens=max_tokens,
        temperature=0.8,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    text = (response.choices[0].message.content or "").strip()
    return text or None

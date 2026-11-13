"""
AutoTube AI - Unified Multi-Provider LLM Gateway (providers/llm.py)
Orchestrates prioritized text generation across free provider chain:
  1. Google Gemini (primary, fast, multimodal)
  2. Groq Llama 3.3 70B (first fallback, ~320 tokens/sec, generous daily limit)
  3. OpenRouter (second fallback, 14-20+ free models)
"""

import os
import time
import requests
import concurrent.futures
import certifi
from dotenv import load_dotenv

os.environ.setdefault("SSL_CERT_FILE", certifi.where())
os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())

from google import genai
from providers.tracker import record_call, record_step_provider

load_dotenv()

try:
    from agents.env_loader import get_gemini_api_key
except ImportError:
    try:
        from env_loader import get_gemini_api_key
    except ImportError:
        def get_gemini_api_key():
            return os.getenv("GEMINI_API_KEY", "")

ACTIVE_MODELS = [
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-pro",
]

OPENAI_MODELS = [
    "gpt-4o-mini",
    "gpt-4o",
]

GROQ_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "mixtral-8x7b-32768",
]

OPENROUTER_MODELS = [
    "openrouter/free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "google/gemini-2.0-flash-exp:free",
    "mistralai/mistral-7b-instruct:free",
    "qwen/qwen-2.5-72b-instruct:free",
]


def call_gemini(prompt: str, api_key: str = None) -> tuple[str, str]:
    """Call Google Gemini API across configured flash models with per-model timeout to avoid hangs."""
    key = api_key or get_gemini_api_key()
    if not key:
        raise ValueError("GEMINI_API_KEY is not configured.")

    client = genai.Client(api_key=key)
    last_err = None

    for model_name in ACTIVE_MODELS:
        t0 = time.time()
        ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        try:
            fut = ex.submit(client.models.generate_content, model=model_name, contents=prompt)
            resp = fut.result(timeout=15.0)

            text = ""
            try:
                text = getattr(resp, "text", "") or ""
            except Exception:
                text = ""

            if not text and hasattr(resp, "candidates") and resp.candidates:
                parts = getattr(resp.candidates[0].content, "parts", [])
                text = "".join(getattr(p, "text", "") for p in parts if getattr(p, "text", None))

            dur_ms = (time.time() - t0) * 1000
            if text and text.strip():
                record_call("gemini", True, duration_ms=dur_ms)
                return text.strip(), f"Gemini ({model_name})"
        except Exception as err:
            dur_ms = (time.time() - t0) * 1000
            err_str = str(err)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                print(f"⚠️ Gemini model {model_name} rate limit (429), failing over immediately ({dur_ms:.0f}ms)...")
            else:
                print(f"⚠️ Gemini model {model_name} notice ({err_str[:80]}), trying next model...")
            last_err = err
            continue
        finally:
            ex.shutdown(wait=False)

    record_call("gemini", False, error=str(last_err))
    raise RuntimeError(f"Gemini cascade failed: {last_err}")


def call_groq(prompt: str, api_key: str = None) -> tuple[str, str]:
    """Call Groq API using Llama 3.3 70B (~320 tokens/sec, generous free tier)."""
    key = api_key or os.getenv("GROQ_API_KEY", "").strip()
    if not key:
        raise ValueError("GROQ_API_KEY is not configured.")

    from groq import Groq
    client = Groq(api_key=key)
    last_err = None

    for model in GROQ_MODELS:
        t0 = time.time()
        try:
            completion = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=2500,
            )
            dur_ms = (time.time() - t0) * 1000
            content = completion.choices[0].message.content or ""
            if content.strip():
                record_call("groq", True, duration_ms=dur_ms)
                return content.strip(), f"Groq ({model})"
        except Exception as err:
            dur_ms = (time.time() - t0) * 1000
            last_err = err
            continue

    record_call("groq", False, error=str(last_err))
    raise RuntimeError(f"Groq API failed: {last_err}")


def call_openrouter(prompt: str, api_key: str = None) -> tuple[str, str]:
    """Call OpenRouter free models cascade."""
    key = api_key or os.getenv("OPENROUTER_API_KEY", "").strip()
    if not key:
        raise ValueError("OPENROUTER_API_KEY is not configured.")

    headers = {
        "Authorization": f"Bearer {key}",
        "HTTP-Referer": "https://autotube.ai",
        "X-Title": "AutoTube AI",
        "Content-Type": "application/json",
    }
    last_err = None

    for model in OPENROUTER_MODELS:
        t0 = time.time()
        try:
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "max_tokens": 2500,
            }
            resp = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=25,
            )
            dur_ms = (time.time() - t0) * 1000
            if resp.status_code == 200:
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                if content and content.strip():
                    record_call("openrouter", True, duration_ms=dur_ms)
                    return content.strip(), f"OpenRouter ({model})"
            else:
                last_err = f"HTTP {resp.status_code}: {resp.text[:120]}"
        except Exception as err:
            last_err = err
            continue

    record_call("openrouter", False, error=str(last_err))
    raise RuntimeError(f"OpenRouter API failed: {last_err}")


def call_openai(prompt: str, api_key: str = None) -> tuple[str, str]:
    """Call OpenAI API using configured OPENAI_API_KEY (gpt-4o-mini / gpt-4o)."""
    key = api_key or os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        raise ValueError("OPENAI_API_KEY is not configured.")

    from openai import OpenAI
    client = OpenAI(api_key=key)
    last_err = None

    for model in OPENAI_MODELS:
        t0 = time.time()
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=2500,
            )
            content = resp.choices[0].message.content or ""
            dur_ms = (time.time() - t0) * 1000
            if content.strip():
                record_call("openai", True, duration_ms=dur_ms)
                return content.strip(), f"OpenAI ({model})"
        except Exception as err:
            dur_ms = (time.time() - t0) * 1000
            last_err = err
            continue

    record_call("openai", False, error=str(last_err))
    raise RuntimeError(f"OpenAI API failed: {last_err}")


def call_pollinations(prompt: str) -> tuple[str, str]:
    """Call Pollinations free text API (100% free, 0 keys needed, multi-model)."""
    t0 = time.time()
    try:
        url = "https://text.pollinations.ai/"
        payload = {
            "messages": [{"role": "user", "content": prompt}],
            "model": "openai-fast",
            "seed": int(time.time()),
        }
        resp = requests.post(url, json=payload, timeout=25)
        if resp.status_code == 200:
            text = resp.text.strip()
            try:
                j = resp.json()
                if "choices" in j and j["choices"]:
                    text = j["choices"][0].get("message", {}).get("content", text)
            except Exception:
                pass
            dur_ms = (time.time() - t0) * 1000
            if text and text.strip():
                record_call("pollinations", True, duration_ms=dur_ms)
                return text.strip(), "Pollinations (Free AI)"
        raise ValueError(f"HTTP {resp.status_code}: {resp.text[:120]}")
    except Exception as err:
        dur_ms = (time.time() - t0) * 1000
        record_call("pollinations", False, error=str(err))
        raise RuntimeError(f"Pollinations AI failed: {err}")


def call_ollama(prompt: str, model: str = None) -> tuple[str, str]:
    """Call local Ollama instance (http://localhost:11434). 100% free, unlimited, zero cloud API fees."""
    t0 = time.time()
    ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    chosen_model = model or os.getenv("OLLAMA_MODEL", "llama3")

    try:
        url = f"{ollama_host}/api/generate"
        payload = {
            "model": chosen_model,
            "prompt": prompt,
            "stream": False,
        }
        resp = requests.post(url, json=payload, timeout=25)
        dur_ms = (time.time() - t0) * 1000
        if resp.status_code == 200:
            data = resp.json()
            text = (data.get("response") or "").strip()
            if text:
                record_call("ollama", True, duration_ms=dur_ms)
                return text, f"Ollama ({chosen_model})"
        record_call("ollama", False, error=f"HTTP {resp.status_code}: {resp.text[:80]}", duration_ms=dur_ms)
        raise RuntimeError(f"Ollama returned HTTP {resp.status_code}")
    except Exception as err:
        dur_ms = (time.time() - t0) * 1000
        record_call("ollama", False, error=str(err), duration_ms=dur_ms)
        raise RuntimeError(f"Ollama local connection failed: {err}")


def generate_text_cascade(prompt: str, api_key: str = None, step_name: str = "script", per_provider_timeout: float = 35.0) -> str:
    """
    Executes free LLM provider chain based on LLM_PROVIDER_ORDER.
    Default order: gemini -> groq -> ollama -> pollinations -> openrouter.
    Enforces per-provider timeout (~35s) so a stalled provider fails over quickly
    rather than consuming the entire stage budget.
    """
    configured_order = os.getenv("LLM_PROVIDER_ORDER", "gemini,groq,ollama,pollinations,openrouter")
    providers = [p.strip().lower() for p in configured_order.split(",") if p.strip()]

    provider_map = {
        "gemini": lambda: call_gemini(prompt, api_key=api_key),
        "groq": lambda: call_groq(prompt),
        "ollama": lambda: call_ollama(prompt),
        "openai": lambda: call_openai(prompt),
        "pollinations": lambda: call_pollinations(prompt),
        "openrouter": lambda: call_openrouter(prompt),
    }

    errors = []
    attempt = 0

    effective_timeout = min(float(per_provider_timeout), 25.0)

    for prov in providers:
        if prov not in provider_map:
            continue
        # Fast skip if credentials are not configured
        if prov == "gemini" and not (api_key or get_gemini_api_key()):
            continue
        if prov == "groq" and not os.getenv("GROQ_API_KEY", "").strip():
            continue
        if prov == "openai" and not os.getenv("OPENAI_API_KEY", "").strip():
            continue
        if prov == "openrouter" and not os.getenv("OPENROUTER_API_KEY", "").strip():
            continue

        attempt += 1
        is_fallback = (attempt > 1)
        t_start = time.time()
        try:
            print(f"🤖 Calling LLM Provider: {prov.upper()}{' (FALLBACK)' if is_fallback else ''} (timeout={effective_timeout:.0f}s)...")
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            try:
                future = executor.submit(provider_map[prov])
                result, label = future.result(timeout=effective_timeout)
            finally:
                executor.shutdown(wait=False)
            dur_ms = (time.time() - t_start) * 1000
            record_step_provider(step_name, label, duration_ms=dur_ms, is_fallback=is_fallback)
            print(f"✅ {label} succeeded in {dur_ms:.0f}ms")
            return result
        except concurrent.futures.TimeoutError:
            dur_ms = (time.time() - t_start) * 1000
            err_msg = f"{prov.upper()} timed out after {per_provider_timeout:.0f}s"
            print(f"⚠️ {err_msg}. Trying next fallback in chain...")
            record_call(prov, False, error=err_msg, duration_ms=dur_ms)
            errors.append(err_msg)
        except Exception as err:
            dur_ms = (time.time() - t_start) * 1000
            print(f"⚠️ {prov.upper()} notice ({err}). Trying next fallback in chain...")
            record_call(prov, False, error=str(err), duration_ms=dur_ms)
            errors.append(f"{prov}: {err}")

    raise RuntimeError(f"All LLM providers in cascade failed: {'; '.join(errors)}")


def generate_multimodal_cascade(prompt: str, image_bytes: bytes, mime_type: str = "image/jpeg", api_key: str = None) -> str:
    """Generate content from an image + text prompt using Gemini models in cascade."""
    key = api_key or get_gemini_api_key()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not configured.")

    client = genai.Client(api_key=key)
    last_err = None

    image_part = genai.types.Part.from_bytes(
        data=image_bytes,
        mime_type=mime_type,
    )

    for model_name in ACTIVE_MODELS:
        try:
            resp = client.models.generate_content(
                model=model_name,
                contents=[prompt, image_part],
            )
            text = getattr(resp, "text", "")
            if text and text.strip():
                return text.strip()
        except Exception as err:
            last_err = err
            continue

    raise RuntimeError(f"All multimodal LLM models in cascade failed. Last error: {last_err}")




# app/openrouter.py
from __future__ import annotations

import base64
import re
from typing import List, Optional

import httpx

from app.config import OPENROUTER_API_KEY, OPENROUTER_BASE_URL

APP_TITLE = "Telegram Design Bot"
APP_REFERER = "http://localhost"

HEADERS = {
    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
    "X-Title": APP_TITLE,
    "HTTP-Referer": APP_REFERER,
}


def _require_key():
    if not OPENROUTER_API_KEY or not OPENROUTER_API_KEY.strip():
        raise RuntimeError("OPENROUTER_API_KEY فارغ. تأكد من .env")


def _short(txt: str, n: int = 1600) -> str:
    return (txt or "")[:n]


def _extract_url_from_text(text: str) -> str | None:
    if not text:
        return None
    m = re.search(r"!\[[^\]]*\]\((https?://[^\s)]+)\)", text)
    if m:
        return m.group(1)
    m = re.search(r"(https?://\S+)", text)
    if m:
        return m.group(1).rstrip(").,")
    return None


async def _post_json(path: str, payload: dict, timeout: int = 180) -> dict:
    _require_key()
    url = f"{OPENROUTER_BASE_URL}{path}"
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(url, headers={**HEADERS, "Content-Type": "application/json"}, json=payload)
        if r.status_code >= 400:
            raise RuntimeError(f"{r.status_code} {url}\n{_short(r.text)}")
        return r.json()


async def _download(url: str) -> bytes:
    async with httpx.AsyncClient(timeout=300) as client:
        r = await client.get(url)
        if r.status_code >= 400:
            raise RuntimeError(f"{r.status_code} GET {url}\n{_short(r.text)}")
        return r.content


def _extract_image_pointer_from_chat(js: dict) -> str | None:
    """
    يحاول استخراج مؤشر صورة (URL أو data:image) من استجابة chat/completions
    الخاصة بنماذج الصور.
    """
    try:
        choice0 = js["choices"][0]
    except Exception:
        return None

    msg = choice0.get("message") or {}

    # 1) message.images
    imgs = msg.get("images") or []
    if isinstance(imgs, list) and imgs:
        for it in imgs:
            iu = (it or {}).get("image_url") or {}
            url = iu.get("url") or (it or {}).get("url")
            if url:
                return url

    # 2) choice.images
    imgs2 = choice0.get("images") or []
    if isinstance(imgs2, list) and imgs2:
        for it in imgs2:
            iu = (it or {}).get("image_url") or {}
            url = iu.get("url") or (it or {}).get("url")
            if url:
                return url

    # 3) message.content parts
    content = msg.get("content")
    if isinstance(content, list):
        for part in content:
            if part.get("type") in ("image_url", "image"):
                iu = part.get("image_url") or {}
                url = iu.get("url") or part.get("url")
                if url:
                    return url
            if "b64_json" in part and part["b64_json"]:
                return "data:image/png;base64," + part["b64_json"]

    # 4) message.content string
    if isinstance(content, str):
        c = content.strip()
        if c.startswith("data:image"):
            return c
        return _extract_url_from_text(c)

    return None


async def _pointer_to_bytes(pointer: str) -> bytes:
    """
    خاص بالصور: pointer قد يكون data:image أو URL.
    """
    if pointer.startswith("data:image"):
        b64 = pointer.split("base64,", 1)[1]
        return base64.b64decode(b64)
    return await _download(pointer)


async def _pointer_to_bytes_any(pointer: str) -> bytes:
    """
    وسائط عامة (صوت/فيديو/صورة...) من data:... أو URL.
    """
    if pointer.startswith("data:"):
        # نتوقع data:audio/...;base64,... أو data:video/...;base64,...
        if "base64," in pointer:
            b64 = pointer.split("base64,", 1)[1]
            return base64.b64decode(b64)
    return await _download(pointer)


def _size_instruction(size: Optional[str]) -> str:
    if not size:
        return (
            "Output exactly ONE image. If you return text, include ONLY the direct image URL "
            "or a data:image base64."
        )
    return (
        f"Output exactly ONE image with resolution {size} (width x height). "
        "If exact size is not possible, keep the same aspect ratio and close resolution. "
        "If you return text, include ONLY the direct image URL or a data:image base64."
    )


def _to_data_url(image_bytes: bytes, mime: str = "image/png") -> str:
    return f"data:{mime};base64," + base64.b64encode(image_bytes).decode("utf-8")


async def chat(model: str, system: str, user: str) -> str:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.7,
    }
    js = await _post_json("/chat/completions", payload, timeout=120)
    content = js["choices"][0]["message"]["content"]
    if isinstance(content, list):
        # بعض الموديلات ترجع content كقائمة أجزاء نصية
        text_out = "".join(
            (part.get("text") or "")
            for part in content
            if isinstance(part, dict) and part.get("type") in (None, "text")
        )
        return text_out or str(content)
    return str(content)


async def image_generate(
    model: str,
    prompt: str,
    size: Optional[str] = "1080x1080",
    input_images: Optional[List[bytes]] = None,
) -> bytes:
    input_images = input_images or []

    base_instruction = f"""{prompt}

IMPORTANT:
- {_size_instruction(size)}
- Do NOT add any logos/watermarks inside the generated image.
"""

    errors = []

    # محاولة 1: chat (نص + صور كأجزاء content)
    try:
        if input_images:
            parts = [{"type": "text", "text": base_instruction}]
            for img in input_images:
                parts.append({"type": "image_url", "image_url": {"url": _to_data_url(img)}})

            payload = {
                "model": model,
                "messages": [{"role": "user", "content": parts}],
            }
        else:
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": base_instruction}],
            }

        js = await _post_json("/chat/completions", payload, timeout=180)
        pointer = _extract_image_pointer_from_chat(js)
        if not pointer:
            raise RuntimeError(f"No image in response: {str(js)[:900]}")
        return await _pointer_to_bytes(pointer)
    except Exception as e:
        errors.append(f"attempt1(chat): {e}")

    # محاولة 2: chat parts بدون صور
    try:
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": [{"type": "text", "text": base_instruction}]}],
        }
        js = await _post_json("/chat/completions", payload, timeout=180)
        pointer = _extract_image_pointer_from_chat(js)
        if not pointer:
            raise RuntimeError(f"No image in response: {str(js)[:900]}")
        return await _pointer_to_bytes(pointer)
    except Exception as e:
        errors.append(f"attempt2(chat parts): {e}")

    # محاولة 3: /completions (كـ fallback)
    if not input_images:
        try:
            payload = {
                "model": model,
                "prompt": base_instruction,
                "max_tokens": 256,
            }
            js = await _post_json("/completions", payload, timeout=180)

            pointer = _extract_image_pointer_from_chat(js)
            if pointer:
                return await _pointer_to_bytes(pointer)

            text = (js.get("choices") or [{}])[0].get("text", "")
            pointer = _extract_url_from_text(text) or (
                text.strip() if text.strip().startswith("data:image") else None
            )
            if not pointer:
                raise RuntimeError(f"No image url in completions response: {str(js)[:900]}")
            return await _pointer_to_bytes(pointer)
        except Exception as e:
            errors.append(f"attempt3(completions): {e}")

    raise RuntimeError("فشل توليد الصورة عبر OpenRouter:\n" + "\n---\n".join(errors))


async def image_edit(
    model: str,
    image_bytes: bytes,
    prompt: str,
    strength: float = 0.3,
    size: Optional[str] = None,
) -> bytes:
    """
    تعديل صورة واحدة بناءً على تعليمات نصية.
    - لا نضيف أي لوجو جديد.
    - لا نغيّر المقاس إلا إذا تم تمرير size.
    """
    data_url = _to_data_url(image_bytes)

    if size:
        size_line = _size_instruction(size)
    else:
        size_line = "Do NOT change the image resolution or aspect ratio."

    instruction = f"""{prompt}

IMPORTANT:
- Keep original layout and overall style as much as possible.
- Apply only the requested changes.
- strength_hint: {strength}
- {size_line}
"""

    errors = []

    # محاولة 1: multimodal parts (نص + صورة)
    try:
        payload = {
            "model": model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": instruction},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }],
        }
        js = await _post_json("/chat/completions", payload, timeout=180)
        pointer = _extract_image_pointer_from_chat(js)
        if not pointer:
            raise RuntimeError(f"No image in response: {str(js)[:900]}")
        return await _pointer_to_bytes(pointer)
    except Exception as e:
        errors.append(f"attempt1(edit multimodal): {e}")

    # محاولة 2: رسالتين (fallback)
    try:
        payload = {
            "model": model,
            "messages": [
                {"role": "user", "content": instruction},
                {"role": "user", "content": [{"type": "image_url", "image_url": {"url": data_url}}]},
            ],
        }
        js = await _post_json("/chat/completions", payload, timeout=180)
        pointer = _extract_image_pointer_from_chat(js)
        if not pointer:
            raise RuntimeError(f"No image in response: {str(js)[:900]}")
        return await _pointer_to_bytes(pointer)
    except Exception as e:
        errors.append(f"attempt2(edit fallback): {e}")

    raise RuntimeError("فشل تعديل الصورة عبر OpenRouter:\n" + "\n---\n".join(errors))


async def audio_generate(model: str, text: str) -> bytes:
    """
    توليد صوت من نص.
    هذه دالة عامة تعتمد على أن الموديل (مثلاً openai/gpt-audio أو نحو ذلك)
    يمكنه إرجاع:
      - إما data:audio/...;base64,...
      - أو رابط مباشر لملف صوتي (mp3/wav/ogg...)
    يجب أن تصيغ برومبت النموذج بحيث يلتزم بإرجاع رابط أو data:audio فقط.
    """
    instruction = f"""{text}

IMPORTANT:
- Generate an audio clip according to the user's request.
- Return ONLY ONE of the following:
    1) A direct HTTP(S) URL to an audio file (e.g. .mp3, .wav, .m4a, .ogg), OR
    2) A data:audio/...;base64,... string.
- Do NOT include any extra text, explanation, or markdown.
"""

    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": instruction},
        ],
    }
    js = await _post_json("/chat/completions", payload, timeout=300)
    msg = (js.get("choices") or [{}])[0].get("message") or {}
    content = msg.get("content")

    if isinstance(content, list):
        # نجمع كل أجزاء النص
        text_out = "".join(
            (part.get("text") or "")
            for part in content
            if isinstance(part, dict) and part.get("type") in (None, "text")
        )
    else:
        text_out = str(content or "")

    text_out = (text_out or "").strip()
    pointer: Optional[str] = None

    if text_out.startswith("data:audio"):
        pointer = text_out
    else:
        pointer = _extract_url_from_text(text_out)

    if not pointer:
        raise RuntimeError(f"لم أستطع استخراج رابط/بيانات صوت من استجابة الموديل:\n{text_out[:500]}")

    return await _pointer_to_bytes_any(pointer)


async def video_generate(model: str, text: str) -> bytes:
    """
    توليد فيديو من نص (أو وصف).
    نفس الفكرة: نعتمد على أن الموديل يرجع:
      - data:video/...;base64,...
      - أو رابط مباشر لملف فيديو (mp4/webm/...).
    يجب صياغة البرومبت ليلتزم بذلك.
    """
    instruction = f"""{text}

IMPORTANT:
- Generate a short video that matches the user's request.
- Return ONLY ONE of the following:
    1) A direct HTTP(S) URL to a video file (e.g. .mp4, .webm), OR
    2) A data:video/...;base64,... string.
- Do NOT include any extra text, explanation, or markdown.
"""

    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": instruction},
        ],
    }
    js = await _post_json("/chat/completions", payload, timeout=600)
    msg = (js.get("choices") or [{}])[0].get("message") or {}
    content = msg.get("content")

    if isinstance(content, list):
        text_out = "".join(
            (part.get("text") or "")
            for part in content
            if isinstance(part, dict) and part.get("type") in (None, "text")
        )
    else:
        text_out = str(content or "")

    text_out = (text_out or "").strip()
    pointer: Optional[str] = None

    if text_out.startswith("data:video"):
        pointer = text_out
    else:
        pointer = _extract_url_from_text(text_out)

    if not pointer:
        raise RuntimeError(f"لم أستطع استخراج رابط/بيانات فيديو من استجابة الموديل:\n{text_out[:500]}")

    return await _pointer_to_bytes_any(pointer)


async def fetch_available_models() -> list[dict]:
    """
    يستعلم قائمة الموديلات من OpenRouter ويعيدها كقائمة dicts.
    نستخدمها لإرسال ملف نصي فيه أسماء الموديلات.
    """
    _require_key()
    url = f"{OPENROUTER_BASE_URL}/models"
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.get(url, headers=HEADERS)
        if r.status_code >= 400:
            raise RuntimeError(f"{r.status_code} {url}\n{_short(r.text)}")
        js = r.json()
        data = js.get("data") if isinstance(js, dict) else js
        if not isinstance(data, list):
            return []
        return data

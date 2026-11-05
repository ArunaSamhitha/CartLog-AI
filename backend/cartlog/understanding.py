"""Turn a photo or a sentence into a structured ProductQuery.

With OPENAI_API_KEY set, a vision-language model reads the image (or the text)
and returns JSON that matches the ProductQuery schema. Without a key, a small
rule-based parser handles text and image search is unavailable.
"""
import base64
import json
import re

from .config import settings
from .schemas import ProductQuery

SYSTEM_PROMPT = """You turn shopping requests into a structured product search.
Return only JSON with these keys:
  product (string, generic name, e.g. "wireless earbuds"),
  brand (string or null), model (string or null),
  attributes (list of short strings: color, size, capacity, material),
  max_price (number in USD or null), condition ("new" | "used" | "any").
If an image is given, identify the main product in it. Read brand names and
model numbers from labels or packaging when they are visible. Never guess a
model number that is not visible."""

_PRICE = re.compile(r"(?:under|below|less than|max|<|budget(?: of)?|up to)\s*\$?\s*(\d+(?:\.\d+)?)\s*(k)?", re.I)
_DOLLAR = re.compile(r"\$\s*(\d+(?:\.\d+)?)")
_FILLER = re.compile(r"\b(find|me|a|an|the|some|i|want|need|looking|for|to|buy|please|cheap|good|best)\b", re.I)


def parse_text_rules(text: str) -> ProductQuery:
    """Keyless fallback: pull out a budget and a condition, keep the rest as the product."""
    max_price = None
    match = _PRICE.search(text) or _DOLLAR.search(text)
    if match:
        max_price = float(match.group(1))
        if match.re is _PRICE and match.group(2):  # "under 1.5k"
            max_price *= 1000
        text = text.replace(match.group(0), " ")
    lowered = text.lower()
    condition = "used" if re.search(r"\b(used|refurb\w*|second[- ]hand|pre-?owned)\b", lowered) else (
        "new" if re.search(r"\bnew\b", lowered) else "any")
    text = re.sub(r"\b(used|refurb\w*|second[- ]hand|pre-?owned|new)\b", " ", text, flags=re.I)
    product = re.sub(r"\s+", " ", _FILLER.sub(" ", text)).strip(" ,.?!") or "product"
    return ProductQuery(product=product, max_price=max_price, condition=condition)


def _client():
    from openai import AsyncOpenAI

    return AsyncOpenAI(api_key=settings.openai_api_key)


async def _structured(messages: list[dict]) -> ProductQuery:
    resp = await _client().chat.completions.create(
        model=settings.vision_model,
        messages=[{"role": "system", "content": SYSTEM_PROMPT}, *messages],
        response_format={"type": "json_object"},
        temperature=0,
        max_tokens=300,
    )
    return ProductQuery.model_validate(json.loads(resp.choices[0].message.content))


async def parse_text(text: str) -> ProductQuery:
    if not settings.llm_enabled:
        return parse_text_rules(text)
    return await _structured([{"role": "user", "content": text}])


async def parse_image(image: bytes, mime: str, note: str | None = None) -> ProductQuery:
    """Vision step: photo (phone camera or smart-glasses capture) -> ProductQuery."""
    if not settings.llm_enabled:
        raise RuntimeError("Image search needs OPENAI_API_KEY. Text search works without it.")
    data_url = f"data:{mime};base64,{base64.b64encode(image).decode()}"
    content = [{"type": "image_url", "image_url": {"url": data_url, "detail": "low"}}]
    if note:
        content.insert(0, {"type": "text", "text": note})
    query = await _structured([{"role": "user", "content": content}])
    if note:  # a typed budget like "under $50" should win over the model's guess
        rules = parse_text_rules(note)
        if rules.max_price is not None:
            query.max_price = rules.max_price
    return query

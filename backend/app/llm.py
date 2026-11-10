"""Model clients. Chat and embeddings both go through OpenRouter's OpenAI-compatible API."""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Any, TypeVar

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from pydantic import BaseModel, ValidationError

from .config import settings

T = TypeVar("T", bound=BaseModel)


class ModelError(RuntimeError):
    """Raised when the LLM or embedding API cannot be reached or returns unusable output."""


def _require_key() -> None:
    if not settings.api_key:
        raise ModelError("OPENROUTER_API_KEY is not set. Copy backend/.env.example to backend/.env and add your key.")


@lru_cache(maxsize=1)
def chat_model() -> ChatOpenAI:
    _require_key()
    return ChatOpenAI(
        model=settings.chat_model,
        api_key=settings.api_key,
        base_url=settings.base_url,
        temperature=settings.chat_temperature,
        timeout=90,
        max_retries=2,
    )


@lru_cache(maxsize=1)
def embedding_model() -> OpenAIEmbeddings:
    _require_key()
    return OpenAIEmbeddings(
        model=settings.embedding_model,
        api_key=settings.api_key,
        base_url=settings.base_url,
        # The model name is an OpenRouter ID, so skip OpenAI's local tiktoken length check.
        check_embedding_ctx_length=False,
        max_retries=2,
    )


def _decode_json_strings(value: Any) -> Any:
    """Some providers return nested lists/objects as JSON-encoded strings inside tool arguments; decode them."""
    if isinstance(value, str) and value.strip()[:1] in "[{":
        try:
            return _decode_json_strings(json.loads(value))
        except json.JSONDecodeError:
            return value
    if isinstance(value, dict):
        return {k: _decode_json_strings(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_decode_json_strings(v) for v in value]
    return value


def structured_call(system_prompt: str, user_prompt: str, schema: type[T]) -> T:
    """One LLM call whose reply must match a Pydantic schema.

    Uses OpenRouter "structured outputs" (response_format = strict JSON schema), so the provider constrains the
    reply to the schema. (Function-calling mode was tried first and sometimes produced malformed nested JSON.)
    """
    runnable = chat_model().with_structured_output(schema, method="json_schema", strict=True, include_raw=True)
    try:
        result = runnable.invoke([SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)])
    except Exception as exc:  # network, auth, rate-limit or provider errors
        raise ModelError(f"Chat model call failed: {exc}") from exc
    if result.get("parsed") is not None:
        return result["parsed"]
    content = getattr(result.get("raw"), "content", "")
    try:
        return schema.model_validate(_decode_json_strings(json.loads(content)))
    except (json.JSONDecodeError, TypeError, ValidationError) as exc:
        raise ModelError(f"Chat model returned an answer in the wrong format: {str(exc)[:300]}") from exc


def vision_structured_call(system_prompt: str, user_prompt: str, image_jpeg_b64: str, schema: type[T]) -> T:
    """Like structured_call, with one page image attached (used to describe figures and tables)."""
    runnable = chat_model().with_structured_output(schema, method="json_schema", strict=True, include_raw=True)
    message = HumanMessage(content=[
        {"type": "text", "text": user_prompt},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_jpeg_b64}"}},
    ])
    try:
        result = runnable.invoke([SystemMessage(content=system_prompt), message])
    except Exception as exc:
        raise ModelError(f"Vision model call failed: {exc}") from exc
    if result.get("parsed") is not None:
        return result["parsed"]
    content = getattr(result.get("raw"), "content", "")
    try:
        return schema.model_validate(_decode_json_strings(json.loads(content)))
    except (json.JSONDecodeError, TypeError, ValidationError) as exc:
        raise ModelError(f"Vision model returned an answer in the wrong format: {str(exc)[:300]}") from exc


def embed_texts(texts: list[str]) -> list[list[float]]:
    try:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), 64):
            vectors.extend(embedding_model().embed_documents(texts[start:start + 64]))
        return vectors
    except Exception as exc:
        raise ModelError(f"Embedding call failed: {exc}") from exc


def embed_query(text: str) -> list[float]:
    try:
        return embedding_model().embed_query(text)
    except Exception as exc:
        raise ModelError(f"Embedding call failed: {exc}") from exc

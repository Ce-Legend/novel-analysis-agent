from __future__ import annotations

import os

from ..config import ProviderName
from ..utils import resolve_api_key
from .base import LLMProvider
from .bailian_long_provider import BailianLongProvider
from .mock import MockProvider
from .openai_provider import OpenAIProvider


def resolve_provider(name: ProviderName | str) -> LLMProvider:
    provider_name = ProviderName(name)
    if provider_name == ProviderName.BAILIAN_LONG:
        return BailianLongProvider()
    if provider_name == ProviderName.MOCK:
        return MockProvider()
    if provider_name == ProviderName.OPENAI:
        return OpenAIProvider()
    if resolve_api_key("OPENAI_API_KEY", "DASHSCOPE_API_KEY"):
        return OpenAIProvider()
    return MockProvider()


def resolve_book_provider(default_provider: LLMProvider, configured_name: ProviderName | None) -> LLMProvider:
    if configured_name in (None, ProviderName.AUTO):
        return default_provider
    if configured_name.value == default_provider.name:
        return default_provider
    return resolve_provider(configured_name)

__all__ = [
    "resolve_provider",
    "resolve_book_provider",
    "LLMProvider",
    "MockProvider",
    "OpenAIProvider",
    "BailianLongProvider",
]

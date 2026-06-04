from __future__ import annotations

from fastapi import FastAPI

from rag.assistant import CarSafetyWhitepaperAssistant
from rag.knowledge_bases import DEFAULT_COLLECTION, validate_collection_name


def get_assistant(app: FastAPI, collection_name: str | None = None) -> CarSafetyWhitepaperAssistant:
    resolved = validate_collection_name(collection_name)
    assistants: dict[str, CarSafetyWhitepaperAssistant] = app.state.assistants
    cached = assistants.get(resolved)
    if cached is not None:
        return cached
    assistant = CarSafetyWhitepaperAssistant(collection_name=resolved)
    assistants[resolved] = assistant
    return assistant


def get_default_assistant(app: FastAPI) -> CarSafetyWhitepaperAssistant:
    return get_assistant(app, DEFAULT_COLLECTION)

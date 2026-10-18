"""Fixed model registry and independent lazy embedding construction."""

from typing import Literal

from app.ai.gemini import EmbeddingGateway, GeminiGateway, GenerationGateway
from app.ai.inetcloud import InetCloudGateway
from app.core.config import Settings
from app.core.errors import ConfigurationError

ModelId = Literal["inetcloud-knowledge", "gemini"]
MODEL_LABELS = {"inetcloud-knowledge": "iNetCloud Knowledge", "gemini": "Gemini"}


def build_generation_gateway(settings: Settings, model_id: ModelId) -> GenerationGateway:
    if model_id == "inetcloud-knowledge":
        return InetCloudGateway(settings)
    if model_id == "gemini":
        return GeminiGateway(settings)
    raise ConfigurationError("Mô hình AI không được hỗ trợ.")


class LazyGeminiEmbedder:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _gateway(self) -> GeminiGateway:
        if not self._settings.gemini_api_key:
            raise ConfigurationError("RAG cần cấu hình Gemini Embedding API key.")
        return GeminiGateway(self._settings)

    def embed_query(self, content: str) -> list[float]:
        gateway = self._gateway()
        try:
            return gateway.embed_query(content)
        finally:
            gateway.close()

    def embed_document(self, title: str, content: str) -> list[float]:
        gateway = self._gateway()
        try:
            return gateway.embed_document(title, content)
        finally:
            gateway.close()


def build_embedding_gateway(settings: Settings) -> EmbeddingGateway:
    return LazyGeminiEmbedder(settings)

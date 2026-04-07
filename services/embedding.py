from typing import List, Optional

from config.settings import settings

try:
    from sentence_transformers import SentenceTransformer  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    SentenceTransformer = None  # type: ignore


_model: Optional["SentenceTransformer"] = None


def load_model() -> "SentenceTransformer":
    """Load and cache local embedding model."""
    global _model
    if SentenceTransformer is None:  # pragma: no cover
        raise RuntimeError("Missing dependency: sentence-transformers")
    if _model is None:
        _model = SentenceTransformer(settings.model_name)
    return _model


def get_embedding(text: str) -> List[float]:
    """Generate embedding vector as list of floats."""
    model = load_model()
    vector = model.encode(text, normalize_embeddings=True)
    return vector.tolist()

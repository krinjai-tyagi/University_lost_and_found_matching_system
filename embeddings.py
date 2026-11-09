import numpy as np

try:
    from sentence_transformers import SentenceTransformer
    AVAILABLE = True
except Exception as error:  # not installed, or a torch problem
    SentenceTransformer = None
    AVAILABLE = False
    print("SBERT disabled, using basic text matching:", error)

MODEL_NAME = "all-MiniLM-L6-v2"   # small and fast (~90 MB, downloads once)

_model = None
_cache = {}   # text -> embedding, so the same text is never encoded twice


def _get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def embed(text):
    text = (text or "").strip().lower()
    if text not in _cache:
        _cache[text] = _get_model().encode(text, normalize_embeddings=True)
    return _cache[text]


def semantic_similarity(a, b):
    """Returns 0..1, or None if SBERT is not available."""
    if not AVAILABLE:
        return None
    sim = float(np.dot(embed(a), embed(b)))  # normalized vectors -> cosine
    return max(0.0, min(1.0, sim)) 

import uuid
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
MAX_SIDE = 800  # saved photos are shrunk to this size (saves space)

try:
    import torch
    from torchvision import models
    AVAILABLE = True
except Exception as error:  # not installed, or a torch problem
    torch = None
    models = None
    AVAILABLE = False
    print("Photo matching disabled:", error)

# Raw cosine between CNN features is never close to 0, even for unrelated
# photos (usually 0.4 - 0.6). So we stretch the range:
#   cosine <= LOW  -> 0% similar,    cosine >= HIGH -> 100% similar
# Tune these two numbers with your own photos (see tune_pair below).
LOW, HIGH = 0.50, 0.90

_model = None
_preprocess = None
_cache = {}   # photo path -> embedding, so a photo is never processed twice


def _get_model():
    global _model, _preprocess
    if _model is None:
        weights = models.MobileNet_V2_Weights.DEFAULT
        _model = models.mobilenet_v2(weights=weights)
        _model.classifier = torch.nn.Identity()  # drop the 1000-class layer
        _model.eval()
        _preprocess = weights.transforms()       # resize + crop + normalize
    return _model, _preprocess


def full_path(image_path):
    return BASE_DIR / image_path


def save_uploaded_image(uploaded_file, folder="uploads", max_side=MAX_SIDE):
    """Saves a Streamlit upload into a folder (default: uploads/).
    Item photos go to 'uploads', proof documents go to 'proofs'.
    Returns the relative path (e.g. 'uploads/ab12.jpg'), or None if the
    file is not a valid image."""
    try:
        img = Image.open(uploaded_file)
        img = ImageOps.exif_transpose(img)   # fix phone photos that are rotated
        img = img.convert("RGB")
    except Exception:
        return None
    img.thumbnail((max_side, max_side))
    (BASE_DIR / folder).mkdir(exist_ok=True)
    name = f"{uuid.uuid4().hex}.jpg"
    img.save(BASE_DIR / folder / name, "JPEG", quality=85)
    return f"{folder}/{name}"


def embed_image(image_path):
    """Returns a normalized embedding for one photo, or None if not possible."""
    if not AVAILABLE or not image_path:
        return None
    if image_path not in _cache:
        path = full_path(image_path)
        if not path.exists():
            return None
        model, preprocess = _get_model()
        img = Image.open(path).convert("RGB")
        with torch.no_grad():
            vec = model(preprocess(img).unsqueeze(0))[0].numpy()
        _cache[image_path] = vec / (np.linalg.norm(vec) + 1e-9)
    return _cache[image_path]


def raw_cosine(path_a, path_b):
    """Plain cosine similarity of two photos (used for tuning)."""
    a, b = embed_image(path_a), embed_image(path_b)
    if a is None or b is None:
        return None
    return float(np.dot(a, b))


def image_similarity(path_a, path_b):
    """Returns 0..1, or None if either photo is missing / model not available."""
    cos = raw_cosine(path_a, path_b)
    if cos is None:
        return None
    return max(0.0, min(1.0, (cos - LOW) / (HIGH - LOW)))


def tune_pair(path_a, path_b):
    """Run this by hand to see the raw numbers for two photos:
        python -c "import image_matching as m; print(m.tune_pair('uploads/a.jpg','uploads/b.jpg'))"
    """
    return raw_cosine(path_a, path_b)
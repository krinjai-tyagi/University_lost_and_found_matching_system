import heapq
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher

from embeddings import AVAILABLE as SBERT_AVAILABLE
from embeddings import semantic_similarity
from image_matching import image_similarity
from union_find import UnionFind

STOP_WORDS = {
    "a", "an", "the", "of", "in", "on", "at", "my", "is", "and", "with",
    "near", "to", "was", "i", "it", "has", "have", "found", "lost",
}

# no photos:   score = text 60% + category 20% + location 20% (+ aging bonus)
W_TEXT, W_CATEGORY, W_LOCATION = 0.6, 0.2, 0.2
# both photos: score = text 40% + photo 30% + category 15% + location 15% (+ aging)
WP_TEXT, WP_IMAGE, WP_CATEGORY, WP_LOCATION = 0.40, 0.30, 0.15, 0.15
MAX_AGING_BONUS = 0.10   # old unmatched items get up to +0.10
AGING_DAYS = 30          # bonus reaches its max after 30 days

# SBERT gives some score even to unrelated items, so the bars are higher
MIN_SCORE = 0.40 if SBERT_AVAILABLE else 0.25
DUP_THRESHOLD = 0.85 if SBERT_AVAILABLE else 0.60


def _words(text):
    found = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {w for w in found if w not in STOP_WORDS}


def _item_text(item):
    # other_type = what the user wrote when the category is "Other"
    return (f"{item.get('title', '')} {item.get('description', '')} "
            f"{item.get('other_type') or ''}").strip()


def _same(a, b):
    return bool(a) and bool(b) and a.strip().lower() == b.strip().lower()


def text_similarity(a, b):
    """Returns 0..1. SBERT meaning score (old method if SBERT is missing)."""
    sbert = semantic_similarity(a, b)
    if sbert is not None:
        return sbert
    wa, wb = _words(a), _words(b)
    overlap = len(wa & wb) / len(wa | wb) if wa and wb else 0.0
    fuzzy = SequenceMatcher(None, (a or "").lower(), (b or "").lower()).ratio()
    return 0.7 * overlap + 0.3 * fuzzy


def aging_bonus(reported_at, now=None):
    """Older unmatched items get a higher priority."""
    try:
        reported = datetime.strptime(reported_at[:19], "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return 0.0
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    days = max((now - reported).days, 0)
    return MAX_AGING_BONUS * min(days, AGING_DAYS) / AGING_DAYS


def score_pair(lost, found, now=None):
    """Returns (score 0..1, list of reasons)."""
    text = text_similarity(_item_text(lost), _item_text(found))
    same_cat = 1.0 if _same(lost.get("category"), found.get("category")) else 0.0
    same_loc = 1.0 if _same(lost.get("location"), found.get("location")) else 0.0
    aging = aging_bonus(lost.get("reported_at"), now)
    image = image_similarity(lost.get("image_path"), found.get("image_path"))  # None = no photo pair

    if image is None:
        base = W_TEXT * text + W_CATEGORY * same_cat + W_LOCATION * same_loc
    else:
        base = (WP_TEXT * text + WP_IMAGE * image
                + WP_CATEGORY * same_cat + WP_LOCATION * same_loc)
    score = min(base + aging, 1.0)

    reasons = []
    if image is not None:
        if image >= 0.7:
            reasons.append(f"Photos look very similar ({image * 100:.0f}%)")
        elif image >= 0.4:
            reasons.append(f"Photos look somewhat similar ({image * 100:.0f}%)")
        else:
            reasons.append(f"Photos look different ({image * 100:.0f}%)")
    if text >= 0.5:
        reasons.append(f"Similar description ({text * 100:.0f}%)")
    shared = sorted(_words(_item_text(lost)) & _words(_item_text(found)))
    if shared:
        reasons.append("Common words: " + ", ".join(shared[:5]))
    if same_cat:
        reasons.append(f"Same category ({found['category']})")
    if same_loc:
        reasons.append(f"Same location ({found['location']})")
    if aging > 0.01:
        reasons.append("Waiting for a while, so priority is boosted")
    if not reasons:
        reasons.append("Weak match")
    return score, reasons


def find_matches(lost_item, found_items, top_n=5, min_score=None, now=None):
    """Top N found items for one lost item, best first.

    Uses a min-heap of size N: the weakest kept match sits on top,
    so a new item only has to beat that one.
    """
    if min_score is None:
        min_score = MIN_SCORE
    heap = []
    for i, found in enumerate(found_items):
        score, reasons = score_pair(lost_item, found, now)
        if score < min_score:
            continue
        entry = (score, i, found, reasons)  # i breaks ties
        if len(heap) < top_n:
            heapq.heappush(heap, entry)
        elif score > heap[0][0]:
            heapq.heapreplace(heap, entry)

    best_first = sorted(heap, key=lambda e: e[0], reverse=True)
    return [
        {"item": found, "score": score, "reason": " | ".join(reasons)}
        for score, _, found, reasons in best_first
    ]


def detect_duplicates(items, threshold=None):
    """Groups repeated reports using Union-Find.

    Two items are duplicates if they have the same category and
    very similar text. Returns a list of groups (lists of item_ids).
    """
    if threshold is None:
        threshold = DUP_THRESHOLD
    uf = UnionFind()
    for item in items:
        uf.find(item["item_id"])

    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            a, b = items[i], items[j]
            if not _same(a.get("category"), b.get("category")):
                continue
            if text_similarity(_item_text(a), _item_text(b)) >= threshold:
                uf.union(a["item_id"], b["item_id"])

    return [ids for ids in uf.groups().values() if len(ids) > 1]
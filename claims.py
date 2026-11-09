"""Claim verification: owner answers a question, finder approves or rejects."""
from db_setup import get_connection
from db_helpers import GUEST_EMAIL
from image_matching import save_uploaded_image
from reputation import (FALSE_CLAIM_PENALTY, FINDER_REWARD,
                        LOW_REPUTATION_LIMIT, change_reputation, get_reputation)

# Hash map: category -> verification question
QUESTIONS = {
    "Wallet": "What cards, cash or photos are inside the wallet?",
    "Phone": "What is the lock-screen wallpaper or phone cover?",
    "Bag": "What items are inside the bag?",
    "Keys": "How many keys are there and what is on the keychain?",
    "ID Card": "What is the full name and ID number on the card?",
    "Electronics": "What is the brand, colour and any mark or sticker on it?",
    "Books": "What is written on the first page or inside the cover?",
    "Clothing": "What brand, size or mark is on it?",
    "Bottle": "What colour is the lid and is there any sticker or dent?",
    "Other": "Describe the item: brand, colour, marks, or what is inside it.",
}
DEFAULT_QUESTION = "Tell one detail about the item that only the owner would know."


def question_for(category):
    return QUESTIONS.get(category, DEFAULT_QUESTION)


# Every claim needs proof of ownership (bill, receipt, warranty card, box photo...),
# not only a written answer.
PROOF_MAX_SIDE = 1600   # proofs are kept bigger than item photos so text stays readable


def get_match_id(lost_id, found_id):
    conn = get_connection()
    row = conn.execute(
        "SELECT match_id FROM matches WHERE lost_item_id = ? AND found_item_id = ?",
        (lost_id, found_id),
    ).fetchone()
    conn.close()
    return row["match_id"] if row else None


def create_claim(match_id, claimant_id, answer, proof_file=None):
    """proof_file = the uploaded proof image (bill, receipt...). It is required.
    Returns (True, message) or (False, error message)."""
    answer = answer.strip()
    if not answer:
        return False, "Please write your answer."
    if get_reputation(claimant_id) < LOW_REPUTATION_LIMIT:
        return False, "Your reputation is too low to make new claims."

    conn = get_connection()
    m = conn.execute(
        """SELECT l.user_id AS owner_id, f.user_id AS finder_id,
                  f.category AS category, uf.email AS finder_email
           FROM matches m
           JOIN items l ON l.item_id = m.lost_item_id
           JOIN items f ON f.item_id = m.found_item_id
           JOIN users uf ON uf.user_id = f.user_id
           WHERE m.match_id = ?""",
        (match_id,),
    ).fetchone()

    if m is None:
        conn.close()
        return False, "Match not found."
    if m["owner_id"] != claimant_id:
        conn.close()
        return False, "Only the person who reported the lost item can claim."
    if m["finder_id"] == claimant_id:
        conn.close()
        return False, "You cannot claim your own found item."
    if m["finder_email"] == GUEST_EMAIL:
        conn.close()
        return False, ("This found item is sample data, so nobody can review the claim. "
                       "Report a found item from another account to test claims.")
    busy = conn.execute(
        "SELECT 1 FROM claims WHERE match_id = ? AND status IN ('pending', 'approved')",
        (match_id,),
    ).fetchone()
    if busy:
        conn.close()
        return False, "A claim for this match is already pending or approved."

    if proof_file is None:
        conn.close()
        return False, ("Please upload proof that this item is yours "
                       "(bill, receipt, warranty card or a clear photo of you with it).")
    proof_path = save_uploaded_image(proof_file, folder="proofs", max_side=PROOF_MAX_SIDE)
    if proof_path is None:
        conn.close()
        return False, "The proof file is not a valid image. Please upload a JPG or PNG."

    conn.execute(
        "INSERT INTO claims (match_id, claimant_id, question, answer, proof_path) "
        "VALUES (?, ?, ?, ?, ?)",
        (match_id, claimant_id, question_for(m["category"]), answer, proof_path),
    )
    conn.commit()
    conn.close()
    return True, "Claim sent! The finder will review your answer."


def get_pending_claims_for_finder(finder_id):
    conn = get_connection()
    rows = conn.execute(
        """SELECT c.claim_id, c.question, c.answer, c.created_at, c.proof_path,
                  u.name AS claimant_name, u.reputation AS claimant_reputation,
                  f.title AS found_title, l.title AS lost_title
           FROM claims c
           JOIN matches m ON m.match_id = c.match_id
           JOIN items f ON f.item_id = m.found_item_id
           JOIN items l ON l.item_id = m.lost_item_id
           JOIN users u ON u.user_id = c.claimant_id
           WHERE f.user_id = ? AND c.status = 'pending'
           ORDER BY c.claim_id""",
        (finder_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_claims_by_claimant(claimant_id):
    conn = get_connection()
    rows = conn.execute(
        """SELECT c.claim_id, c.status, c.question, c.answer, c.created_at,
                  f.title AS found_title
           FROM claims c
           JOIN matches m ON m.match_id = c.match_id
           JOIN items f ON f.item_id = m.found_item_id
           WHERE c.claimant_id = ?
           ORDER BY c.claim_id DESC""",
        (claimant_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def review_claim(claim_id, approve):
    """Finder approves or rejects. Returns (True, message) or (False, error)."""
    conn = get_connection()
    c = conn.execute(
        """SELECT c.claim_id, c.status, c.claimant_id, m.match_id,
                  m.lost_item_id, m.found_item_id, f.user_id AS finder_id
           FROM claims c
           JOIN matches m ON m.match_id = c.match_id
           JOIN items f ON f.item_id = m.found_item_id
           WHERE c.claim_id = ?""",
        (claim_id,),
    ).fetchone()
    if c is None or c["status"] != "pending":
        conn.close()
        return False, "This claim is not pending."

    if approve:
        conn.execute("UPDATE claims SET status = 'approved' WHERE claim_id = ?", (claim_id,))
        conn.execute("UPDATE matches SET status = 'approved' WHERE match_id = ?", (c["match_id"],))
        conn.execute(
            "UPDATE items SET status = 'returned' WHERE item_id IN (?, ?)",
            (c["lost_item_id"], c["found_item_id"]),
        )
        # any other pending claim on the same found item is closed
        conn.execute(
            """UPDATE claims SET status = 'rejected'
               WHERE status = 'pending' AND claim_id != ?
                 AND match_id IN (SELECT match_id FROM matches WHERE found_item_id = ?)""",
            (claim_id, c["found_item_id"]),
        )
        conn.commit()
        conn.close()
        change_reputation(c["finder_id"], FINDER_REWARD, "Returned an item (claim approved)")
        return True, "Claim approved. Item marked as returned."

    conn.execute("UPDATE claims SET status = 'rejected' WHERE claim_id = ?", (claim_id,))
    conn.execute("UPDATE matches SET status = 'rejected' WHERE match_id = ?", (c["match_id"],))
    conn.commit()
    conn.close()
    change_reputation(c["claimant_id"], FALSE_CLAIM_PENALTY, "Claim rejected")
    return True, "Claim rejected."
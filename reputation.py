"""Trust / reputation score (0 to 100). Every user starts at 50."""
from db_setup import get_connection

START_SCORE = 50
MIN_SCORE, MAX_SCORE = 0, 100

FINDER_REWARD = 10          # finder returns an item (claim approved)
FALSE_CLAIM_PENALTY = -5    # your claim was rejected
LOW_REPUTATION_LIMIT = 20   # below this you cannot make new claims


def change_reputation(user_id, points, reason):
    """Adds points (can be negative), keeps score between 0 and 100,
    and writes a line in reputation_log. Returns the new score."""
    conn = get_connection()
    row = conn.execute(
        "SELECT reputation FROM users WHERE user_id = ?", (user_id,)
    ).fetchone()
    if row is None:
        conn.close()
        return None
    old = row["reputation"]
    new = max(MIN_SCORE, min(MAX_SCORE, old + points))
    conn.execute("UPDATE users SET reputation = ? WHERE user_id = ?", (new, user_id))
    conn.execute(
        "INSERT INTO reputation_log (user_id, change, reason) VALUES (?, ?, ?)",
        (user_id, new - old, reason),
    )
    conn.commit()
    conn.close()
    return new


def get_reputation(user_id):
    conn = get_connection()
    row = conn.execute(
        "SELECT reputation FROM users WHERE user_id = ?", (user_id,)
    ).fetchone()
    conn.close()
    return row["reputation"] if row else START_SCORE


def trust_level(score):
    if score >= 70:
        return "Trusted"
    if score >= 40:
        return "Normal"
    return "Low"


def get_reputation_log(user_id, limit=20):
    conn = get_connection()
    rows = conn.execute(
        "SELECT change, reason, created_at FROM reputation_log "
        "WHERE user_id = ? ORDER BY log_id DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
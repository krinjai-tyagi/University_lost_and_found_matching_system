from datetime import datetime, timedelta, timezone

from db_setup import SCHEMA, get_connection

CATEGORIES = ["Wallet", "Phone", "Bag", "Keys", "ID Card", "Electronics",
              "Books", "Clothing", "Bottle", "Other"]
LOCATIONS = ["Library", "Canteen", "Main Gate", "Hostel", "Classroom Block",
             "Sports Ground", "Parking", "Other"]

GUEST_EMAIL = "guest@findralgo.local"


def _add_column(conn, table, column, definition):
    """Adds a column if it is missing (works for old and new databases)."""
    columns = [row["name"] for row in conn.execute(f"PRAGMA table_info({table})")]
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _migrate(conn):
    _add_column(conn, "items", "image_path", "TEXT")   # photo of the item
    _add_column(conn, "items", "other_type", "TEXT")   # text written when category = Other
    _add_column(conn, "claims", "proof_path", "TEXT")  # proof uploaded by the claimant


def category_label(item):
    """'Other' items show what the user wrote, e.g. 'Other (Umbrella)'."""
    if item.get("category") == "Other" and item.get("other_type"):
        return f"Other ({item['other_type']})"
    return item.get("category") or ""


def init_db():
    conn = get_connection()
    conn.executescript(SCHEMA)
    _migrate(conn)
    _guest_user_id(conn)  # demo/sample data belongs to this user
    conn.commit()
    conn.close()


def _guest_user_id(conn):
    row = conn.execute("SELECT user_id FROM users WHERE email = ?", (GUEST_EMAIL,)).fetchone()
    if row:
        return row["user_id"]
    cur = conn.execute(
        "INSERT INTO users (name, email, password) VALUES (?, ?, ?)",
        ("Guest", GUEST_EMAIL, "none"),
    )
    return cur.lastrowid


def add_item(item_type, title, description, category, location,
             reported_at=None, user_id=None, image_path=None, other_type=None):
    conn = get_connection()
    if user_id is None:
        user_id = _guest_user_id(conn)
    columns = ["user_id", "item_type", "title", "description", "category",
               "location", "image_path", "other_type"]
    values = [user_id, item_type, title, description, category,
              location, image_path, other_type]
    if reported_at:
        columns.append("reported_at")
        values.append(reported_at)
    marks = ", ".join("?" * len(values))
    cur = conn.execute(
        f"INSERT INTO items ({', '.join(columns)}) VALUES ({marks})", values
    )
    conn.commit()
    item_id = cur.lastrowid
    conn.close()
    return item_id


def get_items(item_type=None, status="open"):
    query = "SELECT * FROM items WHERE status = ?"
    params = [status]
    if item_type:
        query += " AND item_type = ?"
        params.append(item_type)
    query += " ORDER BY reported_at DESC"
    conn = get_connection()
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_matches(lost_id, matches):
    """Saves matches into the matches table (skips pairs already saved)."""
    conn = get_connection()
    for m in matches:
        found_id = m["item"]["item_id"]
        exists = conn.execute(
            "SELECT 1 FROM matches WHERE lost_item_id = ? AND found_item_id = ?",
            (lost_id, found_id),
        ).fetchone()
        if not exists:
            conn.execute(
                "INSERT INTO matches (lost_item_id, found_item_id, score, reason) VALUES (?, ?, ?, ?)",
                (lost_id, found_id, m["score"], m["reason"]),
            )
    conn.commit()
    conn.close()


def add_sample_data():
    """Adds demo items. Returns how many were added (0 if already added)."""
    conn = get_connection()
    done = conn.execute(
        "SELECT 1 FROM items WHERE title = 'Black leather wallet' AND item_type = 'lost'"
    ).fetchone()
    conn.close()
    if done:
        return 0

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    def ago(days):
        return (now - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")

    samples = [
        ("lost", "Black leather wallet", "Black wallet with college ID card inside", "Wallet", "Library", ago(12)),
        ("lost", "Black leather wallet", "black wallet with college id card inside", "Wallet", "Library", ago(11)),
        ("lost", "Blue water bottle", "Blue steel bottle with a sticker", "Bottle", "Canteen", ago(3)),
        ("lost", "Samsung phone", "Black Samsung phone with cracked screen guard", "Phone", "Main Gate", ago(1)),
        ("found", "Wallet found", "Black leather wallet with ID card", "Wallet", "Library", ago(2)),
        ("found", "Steel water bottle", "Blue bottle with sticker, left in canteen", "Bottle", "Canteen", ago(1)),
        ("found", "Mobile phone", "Black Samsung mobile with cracked screen guard", "Phone", "Hostel", ago(0)),
        ("found", "Red umbrella", "Red umbrella near the parking area", "Other", "Parking", ago(0)),
    ]
    for s in samples:
        add_item(*s)
    return len(samples)
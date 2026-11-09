"""Signup and login. Passwords are stored hashed, never as plain text."""
import hashlib
import hmac
import os
import re

from db_setup import get_connection

ITERATIONS = 100_000


def hash_password(password, salt=None):
    """Returns 'salt$hash'. A new random salt is used for every user."""
    salt = salt or os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt), ITERATIONS
    ).hex()
    return f"{salt}${digest}"


def check_password(password, stored):
    if "$" not in stored:
        return False
    salt, digest = stored.split("$", 1)
    new_digest = hash_password(password, salt).split("$", 1)[1]
    return hmac.compare_digest(new_digest, digest)


def register_user(name, email, password):
    """Returns (True, user_id) or (False, error message)."""
    name = name.strip()
    email = email.strip().lower()
    if not name:
        return False, "Please enter your name."
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        return False, "Please enter a valid email."
    if len(password) < 6:
        return False, "Password must be at least 6 characters."

    conn = get_connection()
    try:
        if conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
            return False, "This email is already registered. Please log in."
        cur = conn.execute(
            "INSERT INTO users (name, email, password) VALUES (?, ?, ?)",
            (name, email, hash_password(password)),
        )
        conn.commit()
        return True, cur.lastrowid
    finally:
        conn.close()


def login_user(email, password):
    """Returns the user as a dict, or None if email/password is wrong."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM users WHERE email = ?", (email.strip().lower(),)
    ).fetchone()
    conn.close()
    if row and check_password(password, row["password"]):
        return {"user_id": row["user_id"], "name": row["name"], "email": row["email"]}
    return None


def get_user(user_id):
    conn = get_connection()
    row = conn.execute(
        "SELECT user_id, name, email, reputation FROM users WHERE user_id = ?", (user_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None
    
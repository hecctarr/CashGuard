"""
Sign-in and access control.

- Passwords are never stored. We store a random salt and a PBKDF2-SHA256 hash (200,000 rounds).
- Each role can only open its own pages. The app checks this on every page, not just in the menu,
  so a Manager or Employee can never reach an Owner page.
- Demo accounts are created on first run. The Owner can add people, reset passwords and remove
  accounts in Settings → Team & sign-in.

Production: replace this with Supabase Auth (see supabase/schema.sql); the role checks stay the same.
"""

import hashlib
import hmac
import secrets

ROUNDS = 200_000
ROLES = ("Owner", "Manager", "Employee")

# Which pages each role may open. Anything not listed is blocked.
PAGES = {
    "Owner": ["Dashboard", "Review & decide", "Invoices", "What-if simulator",
              "Does it work? (Test)", "Upload bill", "Audit log", "Settings"],
    "Manager": ["Review & decide", "Upload bill", "New expense request", "My submissions"],
    "Employee": ["Upload bill", "New expense request", "My submissions"],
}
OWNER_ONLY = [p for p in PAGES["Owner"] if p not in PAGES["Manager"] + PAGES["Employee"]]

# Demo accounts (shown on the sign-in page so judges can try every role)
DEMO_ACCOUNTS = [
    ("owner", "owner123", "Business Owner", "Owner"),
    ("manager", "manager123", "Shift Manager", "Manager"),
    ("staff", "staff123", "Staff Member", "Employee"),
]


def can_open(role: str, page: str) -> bool:
    return page in PAGES.get(role, [])


def hash_password(password: str, salt: str = None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), ROUNDS).hex()
    return salt, digest


def make_user(username: str, password: str, name: str, role: str) -> dict:
    if role not in ROLES:
        raise ValueError(role)
    salt, digest = hash_password(password)
    return {"username": username.strip().lower(), "name": name.strip(), "role": role,
            "salt": salt, "hash": digest}


def ensure_users(settings: dict) -> bool:
    """Add the demo accounts if no accounts exist yet. Returns True if settings changed."""
    if settings.get("users"):
        return False
    settings["users"] = [make_user(u, p, n, r) for u, p, n, r in DEMO_ACCOUNTS]
    return True


def find(settings: dict, username: str):
    username = (username or "").strip().lower()
    return next((u for u in settings.get("users", []) if u["username"] == username), None)


def verify(settings: dict, username: str, password: str):
    """Return the user (without salt/hash) if the password is right, else None."""
    u = find(settings, username)
    if not u or not password:
        hash_password(password or "x")          # same work either way (no timing hint)
        return None
    _, digest = hash_password(password, u["salt"])
    if not hmac.compare_digest(digest, u["hash"]):
        return None
    return {"id": u["username"], "name": u["name"], "role": u["role"]}


def check_new_password(password: str) -> str:
    """Return a problem message, or '' if the password is acceptable."""
    if len(password) < 8:
        return "Password must be at least 8 characters."
    if password.lower() in {p for _, p, _, _ in DEMO_ACCOUNTS} | {"password", "12345678"}:
        return "Please choose a less common password."
    return ""


def owners(settings: dict) -> int:
    return sum(1 for u in settings.get("users", []) if u["role"] == "Owner")

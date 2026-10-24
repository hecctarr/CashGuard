"""Sign-in and access-control tests."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import auth  # noqa: E402


def test_passwords_are_hashed_and_checked():
    s = {}
    assert auth.ensure_users(s)
    owner = auth.find(s, "owner")
    assert "owner123" not in str(owner)                    # never stored as text
    assert auth.verify(s, "owner", "owner123")["role"] == "Owner"
    assert auth.verify(s, "OWNER ", "owner123")            # username not case-sensitive
    assert auth.verify(s, "owner", "wrong") is None
    assert auth.verify(s, "nobody", "owner123") is None
    assert not auth.ensure_users(s)                        # existing accounts are kept


def test_staff_and_manager_cannot_open_owner_pages():
    for page in auth.OWNER_ONLY:
        assert auth.can_open("Owner", page)
        assert not auth.can_open("Manager", page)
        assert not auth.can_open("Employee", page)
    assert {"Dashboard", "Settings", "Audit log"} <= set(auth.OWNER_ONLY)
    assert not auth.can_open("Hacker", "Dashboard")


def test_weak_passwords_rejected():
    assert auth.check_new_password("short")
    assert auth.check_new_password("owner123")
    assert auth.check_new_password("Kopi-Bean-2026") == ""

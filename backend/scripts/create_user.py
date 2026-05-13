"""Create or update a backend login (admin/user).

Use this instead of an HTTP register endpoint — the only way to mint accounts
is local CLI access to the DB, so the system stays invite-only by you.

Run from backend/:
    uv run python scripts/create_user.py --username alice
    uv run python scripts/create_user.py --username alice --role admin

Password is read via getpass (no echo, not in shell history).
If the user already exists, the password is updated in place; role is kept.
"""
from __future__ import annotations

import argparse
import getpass
import sys

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]


def main() -> int:
    parser = argparse.ArgumentParser(description="Create or update a backend user.")
    parser.add_argument("--username", required=True)
    parser.add_argument(
        "--role",
        choices=["admin", "user"],
        default="user",
        help="Role to assign on create (ignored on update). Default: user.",
    )
    args = parser.parse_args()

    from sqlmodel import Session

    from steel_backend.auth.password import hash_password
    from steel_backend.config import get_settings
    from steel_backend.storage.models import User
    from steel_backend.storage.sqlite_store import SqliteUserStore, init_db

    cfg = get_settings()
    engine = init_db(cfg.database_url)
    store = SqliteUserStore(engine)

    existing = store.get_by_username(args.username)

    pw = getpass.getpass("Password: ")
    pw2 = getpass.getpass("Confirm:  ")
    if pw != pw2:
        print("ERROR: passwords do not match", file=sys.stderr)
        return 1
    if len(pw) < 8:
        print("ERROR: password must be at least 8 characters", file=sys.stderr)
        return 1

    hashed = hash_password(pw)

    if existing is None:
        store.create(username=args.username, password_hash=hashed, role=args.role)
        print(f"OK created user '{args.username}' (role={args.role})")
        return 0

    with Session(engine) as s:
        user = s.get(User, existing.id)
        assert user is not None
        user.password_hash = hashed
        s.add(user)
        s.commit()
    print(f"OK updated password for '{args.username}' (role unchanged: {existing.role})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

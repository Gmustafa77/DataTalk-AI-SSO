"""Create the password hash for one DataTalk.AI login user and, optionally, add the user to ``.env``.

Run from the project root; the password is typed hidden and is never printed or stored::

    uv run python scripts/hash_password.py --env-file .env      # local: adds/updates the user in .env
    uv run python scripts/hash_password.py                       # just print the snippets
    uv run python scripts/hash_password.py --username jsmith --name "Jane Smith" --role analyst

* ``--env-file .env`` merges the user into the ``LOGIN_USERS`` line (other users and all other lines are
  left exactly as they are). Then set ``LOGIN_ENABLED=true`` and restart the app.
* The printed ``[login.users.<username>]`` block is for Streamlit's *Secrets* box (Community Cloud) or
  ``.streamlit/secrets.toml``.

Only the hash is stored, never the password. To change a password, run this again for the same username.
"""
from __future__ import annotations

import argparse
import getpass
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make `core` importable from scripts/

from core.auth import hash_password, normalise_username, password_problems  # noqa: E402

_LINE = re.compile(r"^[ \t]*LOGIN_USERS[ \t]*=[^\r\n]*", re.M)


def _clean(text: str) -> str:
    """Drop characters that would need escaping inside a single-quoted .env value."""
    return re.sub(r"[\\'\"\r\n]", "", text).strip()


def merge_env_file(path: Path, username: str, entry: dict) -> None:
    """Add or replace ``username`` in the ``LOGIN_USERS`` JSON line of ``path`` (created if missing)."""
    text = ""
    if path.exists():
        with path.open("r", encoding="utf-8", newline="") as fh:  # newline="" keeps CRLF files unchanged
            text = fh.read()
    users: dict = {}
    match = _LINE.search(text)
    if match:
        raw = match.group(0).split("=", 1)[1].strip()
        if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "'\"":
            raw = raw[1:-1]
        try:
            users = json.loads(raw) if raw else {}
        except ValueError:
            raise SystemExit("The existing LOGIN_USERS line is not valid JSON; fix or delete it and run again.") from None
        if not isinstance(users, dict):
            raise SystemExit("The existing LOGIN_USERS value is not a JSON object.")
    users[username] = entry
    line = "LOGIN_USERS='" + json.dumps(users, separators=(",", ":")) + "'"
    if match:
        text = text[:match.start()] + line + text[match.end():]
    else:
        newline = "\r\n" if "\r\n" in text else "\n"
        text = text + ("" if not text or text.endswith(("\n", "\r")) else newline) + line + newline
    with path.open("w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--username", help="login name (case-insensitive)")
    parser.add_argument("--name", help="display name shown in the app")
    parser.add_argument("--role", default="", help="optional role label")
    parser.add_argument("--env-file", type=Path, help="add the user to LOGIN_USERS in this file, e.g. .env")
    args = parser.parse_args()

    username = normalise_username(args.username or input("Username: "))
    if not re.fullmatch(r"[a-z0-9._@\-]{1,64}", username):
        print("Username may contain only letters, digits and . _ @ - (max 64 characters).", file=sys.stderr)
        return 2
    display = _clean(args.name or input(f"Display name [{username}]: ") or username) or username
    role = _clean(args.role)

    password = getpass.getpass("Password (hidden): ")
    problems = password_problems(password)
    if problems:
        print("Password rejected: " + "; ".join(problems) + ".", file=sys.stderr)
        return 2
    if getpass.getpass("Repeat password: ") != password:
        print("The passwords do not match.", file=sys.stderr)
        return 2

    entry = {"name": display, "password_hash": hash_password(password)}
    if role:
        entry["role"] = role

    if args.env_file:
        merge_env_file(args.env_file, username, entry)
        print(f"\nUser '{username}' saved in {args.env_file}. Make sure it also contains LOGIN_ENABLED=true, then restart the app.")

    header = f"[login.users.{username}]" if re.fullmatch(r"[A-Za-z0-9_\-]+", username) else f'[login.users."{username}"]'
    print("\nFor Streamlit Secrets (Community Cloud) or .streamlit/secrets.toml, add:\n")
    print(header)
    print(f'name = "{display}"')
    if role:
        print(f'role = "{role}"')
    print(f'password_hash = "{entry["password_hash"]}"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
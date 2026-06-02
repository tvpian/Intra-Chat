#!/usr/bin/env python3
"""
Interactive setup for Intra-Chat. Writes APP_PASSWORD and SECRET_KEY into a
local `.env` file alongside this script.

Usage:
    python setup_password.py
"""

import getpass
import os
import secrets
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(HERE, ".env")
EXAMPLE_PATH = os.path.join(HERE, ".env.example")


def main() -> int:
    print("Intra-Chat — initial setup")
    print("=" * 32)

    if os.path.exists(ENV_PATH):
        choice = input(".env already exists. Overwrite? (y/N): ").strip().lower()
        if choice != "y":
            print("Cancelled.")
            return 0

    while True:
        password = getpass.getpass("Choose a login password (min 8 chars): ")
        if len(password) < 8:
            print("  Password must be at least 8 characters.")
            continue
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            print("  Passwords do not match.")
            continue
        break

    secret_key = secrets.token_hex(32)

    base = ""
    if os.path.exists(EXAMPLE_PATH):
        with open(EXAMPLE_PATH) as f:
            base = f.read()
        base = base.replace("change_me_to_a_long_passphrase", password)
        base = base.replace("replace_with_random_64_hex_chars", secret_key)
    else:
        base = (
            f"APP_PASSWORD={password}\n"
            f"SECRET_KEY={secret_key}\n"
            "HOST=0.0.0.0\n"
            "PORT=5656\n"
        )

    with open(ENV_PATH, "w") as f:
        f.write(base)
    os.chmod(ENV_PATH, 0o600)

    print(f"\n✅  Wrote {ENV_PATH} (chmod 600)")
    print("Next:")
    print("    pip install -r requirements.txt")
    print("    python app.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())

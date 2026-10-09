#!/usr/bin/env python3
"""One-shot environment bootstrap for the API-6 backend.

Creates .env from .env.example, replacing every <...> placeholder with a
strong random secret, and writes CREDENTIALS.txt so the generated values
can be saved to a password manager (delete that file afterwards).

No local Python needed — run it through Docker from the backend folder:

  Linux/macOS:
    docker run --rm --user "$(id -u):$(id -g)" -v "$(pwd):/app" -w /app python:3.12-slim python scripts/setup_env.py

  Windows (PowerShell):
    docker run --rm -v "${PWD}:/app" -w /app python:3.12-slim python scripts/setup_env.py
"""

import secrets
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_EXAMPLE = ROOT / ".env.example"
ENV_FILE = ROOT / ".env"
CREDENTIALS_FILE = ROOT / "CREDENTIALS.txt"

CREDENTIALS_TEMPLATE = """API-6 BACKEND - GENERATED CREDENTIALS
=====================================
Generated on: {today}

SECURITY NOTICE (LGPD):
This file is listed in .gitignore and must NEVER be committed.
Save these credentials in a secure place (password manager) and
DELETE this file afterwards. The same values are already set in
your local .env file, which is also ignored by Git.

--- PostgreSQL ---
Host:     localhost (from your machine) / postgres (inside Docker)
Port:     {POSTGRES_PORT}
Database: {POSTGRES_DB}
User:     {POSTGRES_USER}
Password: {POSTGRES_PASSWORD}

--- MongoDB ---
Host:     localhost (from your machine) / mongodb (inside Docker)
Port:     {MONGO_PORT}
Database: {MONGO_DB}
User:     {MONGO_USER}
Password: {MONGO_PASSWORD}

--- Django admin (http://localhost:{API_PORT}/admin/) ---
User:     {DJANGO_SUPERUSER_USERNAME}
Password: {DJANGO_SUPERUSER_PASSWORD}

--- Django ---
SECRET_KEY: {DJANGO_SECRET_KEY}
Excluded-identifier HMAC key: {EXCLUDED_IDENTIFIER_HMAC_KEY}
"""


def generate_value(key: str) -> str:
    # 64 hex chars for the signing key, 32 for passwords (128+ bits either way)
    return secrets.token_hex(32 if key in ("DJANGO_SECRET_KEY", "EXCLUDED_IDENTIFIER_HMAC_KEY") else 16)


def main() -> int:
    force = "--force" in sys.argv

    if not ENV_EXAMPLE.exists():
        print("ERROR: .env.example not found. Run this from the backend folder.")
        return 1

    if ENV_FILE.exists() and not force:
        print("ERROR: .env already exists and will not be overwritten.")
        print("Delete it first, or re-run with --force to regenerate everything.")
        print("NOTE: databases that were already initialized keep their old")
        print("passwords; after regenerating you must run 'docker compose down -v'")
        print("(which DELETES all database data) before 'docker compose up'.")
        return 1

    env_lines = []
    generated = []
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if "=" in stripped and not stripped.startswith("#"):
            key, value = stripped.split("=", 1)
            if value.startswith("<") and value.endswith(">"):
                line = f"{key}={generate_value(key)}"
                generated.append(key)
        env_lines.append(line)

    ENV_FILE.write_text("\n".join(env_lines) + "\n", encoding="utf-8")

    env = {}
    for line in env_lines:
        if "=" in line and not line.strip().startswith("#"):
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip()

    CREDENTIALS_FILE.write_text(
        CREDENTIALS_TEMPLATE.format(today=date.today().isoformat(), **env),
        encoding="utf-8",
    )

    print(f"Created .env ({len(generated)} secrets generated: {', '.join(generated)})")
    print("Created CREDENTIALS.txt — save it in a password manager, then DELETE it.")
    print("Next step: docker compose up --build")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Re-write every integration's stored credentials with the current key.

Covers two jobs:

  * **Backfill** — rows written before envelope encryption are cleartext JSON.
    Running this once after setting ``INTEGRATION_CREDENTIALS_KEY`` upgrades
    them in place.
  * **Rotation** — deploy with ``INTEGRATION_CREDENTIALS_KEY=new,old``, run this
    to re-encrypt everything under ``new``, then drop ``old`` and redeploy.

Idempotent: rows already sealed under the current primary key are re-sealed
harmlessly. Credential values are never printed.

Usage (from backend/):
  python -m scripts.encrypt_integration_credentials
  python -m scripts.encrypt_integration_credentials --dry-run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running as a module from backend/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import SessionLocal  # noqa: E402
from models.models import DataSourceIntegration  # noqa: E402
from services.integration_credentials import (  # noqa: E402
    IntegrationCredentialsError,
    decrypt_config,
    encrypt_config,
    encryption_enabled,
    is_encrypted,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change without writing",
    )
    args = parser.parse_args()

    if not encryption_enabled():
        print(
            "INTEGRATION_CREDENTIALS_KEY is not set, so there is nothing to encrypt with.\n"
            "Generate a key with:\n"
            '  python -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())"',
            file=sys.stderr,
        )
        return 2

    db = SessionLocal()
    encrypted = 0
    resealed = 0
    empty = 0
    failed: list[dict[str, str]] = []

    try:
        for row in db.query(DataSourceIntegration).all():
            was_encrypted = is_encrypted(row.config_json)
            try:
                config = decrypt_config(row.config_json)
            except IntegrationCredentialsError as e:
                failed.append({"id": row.id, "provider": row.provider, "error": str(e)})
                continue

            if not config:
                empty += 1
                continue

            if not args.dry_run:
                row.config_json = encrypt_config(config)

            if was_encrypted:
                resealed += 1
            else:
                encrypted += 1

        if not args.dry_run:
            db.commit()
    finally:
        db.close()

    verb = "would encrypt" if args.dry_run else "encrypted"
    print(f"{verb} (was cleartext): {encrypted}")
    print(f"re-sealed under current key: {resealed}")
    print(f"skipped (no credentials stored): {empty}")
    if failed:
        print(f"\nunreadable: {len(failed)} — these need the old key, or a reconnect:")
        for item in failed:
            print(f"  {item['id']} ({item['provider']}): {item['error']}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

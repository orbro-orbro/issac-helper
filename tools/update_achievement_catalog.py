"""Maintenance command for safely refreshing the merged achievement catalog."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.catalog_update import update_achievement_catalog
from app.discovery import discover_accounts


def _discovered_schema() -> Path | None:
    return next(
        (
            account.schema_path
            for account in discover_accounts()
            if account.schema_path.is_file()
        ),
        None,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema", type=Path, default=None)
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "data" / "catalog" / "achievements.json",
    )
    parser.add_argument(
        "--icons-dir",
        type=Path,
        default=PROJECT_ROOT / "web" / "assets" / "achievements",
    )
    args = parser.parse_args()
    schema = args.schema or _discovered_schema()
    if schema is None:
        parser.error("no local Steam achievement schema was discovered; pass --schema")

    result = update_achievement_catalog(
        schema_path=schema,
        catalog_path=args.output,
        icons_dir=args.icons_dir,
    )
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    raise SystemExit(0 if result.ok else 1)


if __name__ == "__main__":
    main()

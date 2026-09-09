"""Maintenance command: refresh the checked-in wiki.gg achievement snapshot."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
from urllib.request import Request, urlopen

from app.wiki_catalog import DEFAULT_PATH, SOURCE_URL, parse_achievement_table


API_URL = (
    "https://bindingofisaacrebirth.wiki.gg/api.php"
    "?action=parse&page=Achievements&prop=text&format=json&formatversion=2"
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_PATH)
    args = parser.parse_args()
    request = Request(API_URL, headers={"User-Agent": "IsaacHelper/0.1 catalog maintenance"})
    with urlopen(request, timeout=30) as response:
        api_payload = json.load(response)
    html = api_payload["parse"]["text"]
    records = parse_achievement_table(html)
    if len(records) < 600:
        raise RuntimeError(f"refusing incomplete catalog with only {len(records)} rows")
    payload = {
        "source": SOURCE_URL,
        "retrieved_at": datetime.now(tz=timezone.utc).isoformat(),
        "achievements": [records[item] for item in sorted(records)],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=args.output.parent, suffix=".tmp", delete=False
        ) as handle:
            temp_name = handle.name
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        Path(temp_name).replace(args.output)
        temp_name = None
    finally:
        if temp_name:
            Path(temp_name).unlink(missing_ok=True)
    print(f"Wrote {len(records)} achievements to {args.output}")


if __name__ == "__main__":
    main()

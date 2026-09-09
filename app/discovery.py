"""Discover local Steam accounts and Isaac save slots without changing them."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Iterable, Sequence

from . import APP_ID


class DiscoveryError(ValueError):
    """Raised when a requested local account or slot is unavailable."""


@dataclass(frozen=True)
class SlotInfo:
    number: int
    save_path: Path
    modified_at: datetime
    size: int

    def as_dict(self) -> dict[str, object]:
        return {
            "number": self.number,
            "filename": self.save_path.name,
            "modified_at": self.modified_at.isoformat(),
            "size": self.size,
        }


@dataclass(frozen=True)
class AccountInfo:
    id: str
    steam_root: Path
    stats_path: Path
    schema_path: Path
    game_dir: Path
    save_dir: Path
    slots: tuple[SlotInfo, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "has_stats": self.stats_path.is_file(),
            "has_schema": self.schema_path.is_file(),
            "slots": [slot.as_dict() for slot in self.slots],
        }


@dataclass(frozen=True)
class Selection:
    account: AccountInfo
    slot: SlotInfo


def _unique_paths(paths: Iterable[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path).casefold().rstrip("\\/")
        if key and key not in seen:
            seen.add(key)
            result.append(path)
    return result


def default_steam_roots() -> list[Path]:
    candidates: list[Path] = []
    configured = os.environ.get("ISAAC_STEAM_ROOT")
    if configured:
        candidates.append(Path(configured))
    candidates.append(Path(r"D:\steam"))
    program_files = os.environ.get("ProgramFiles(x86)")
    if program_files:
        candidates.append(Path(program_files) / "Steam")
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
            candidates.append(Path(winreg.QueryValueEx(key, "SteamPath")[0]))
    except (ImportError, FileNotFoundError, OSError):
        pass
    return _unique_paths(candidates)


def read_savedata_path(game_dir: Path) -> Path | None:
    info_file = Path(game_dir) / "savedatapath.txt"
    try:
        lines = info_file.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    except OSError:
        return None
    for line in lines:
        if line.casefold().startswith("save data path:"):
            value = line.split(":", 1)[1].strip().replace("/", os.sep)
            return Path(value) if value else None
    return None


def _slots_in(directory: Path) -> tuple[SlotInfo, ...]:
    slots: list[SlotInfo] = []
    for number in (1, 2, 3):
        path = directory / f"rep+persistentgamedata{number}.dat"
        if not path.is_file():
            continue
        stat = path.stat()
        slots.append(SlotInfo(
            number=number,
            save_path=path,
            modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
            size=stat.st_size,
        ))
    return tuple(slots)


def discover_accounts(
    steam_roots: Sequence[Path] | None = None,
) -> list[AccountInfo]:
    roots = _unique_paths(Path(path) for path in (steam_roots or default_steam_roots()))
    accounts: dict[str, AccountInfo] = {}
    for root in roots:
        userdata = root / "userdata"
        if not userdata.is_dir():
            continue
        game_dir = root / "steamapps" / "common" / "The Binding of Isaac Rebirth"
        fallback_save_dir = read_savedata_path(game_dir)
        for account_dir in userdata.iterdir():
            if not account_dir.is_dir() or not account_dir.name.isdigit():
                continue
            app_dir = account_dir / APP_ID
            if not app_dir.is_dir():
                continue
            cloud_dir = app_dir / "remote"
            slots = _slots_in(cloud_dir)
            save_dir = cloud_dir
            if not slots and fallback_save_dir:
                slots = _slots_in(fallback_save_dir)
                save_dir = fallback_save_dir
            stats_dir = root / "appcache" / "stats"
            candidate = AccountInfo(
                id=account_dir.name,
                steam_root=root,
                stats_path=stats_dir / f"UserGameStats_{account_dir.name}_{APP_ID}.bin",
                schema_path=stats_dir / f"UserGameStatsSchema_{APP_ID}.bin",
                game_dir=game_dir,
                save_dir=save_dir,
                slots=slots,
            )
            previous = accounts.get(candidate.id)
            if previous is None or (not previous.slots and candidate.slots):
                accounts[candidate.id] = candidate
    return sorted(accounts.values(), key=lambda item: int(item.id))


def resolve_selection(
    account_id: str,
    slot: int,
    accounts: Sequence[AccountInfo],
) -> Selection:
    if not isinstance(account_id, str) or not account_id.isdigit():
        raise DiscoveryError("unknown Steam account")
    account = next((item for item in accounts if item.id == account_id), None)
    if account is None:
        raise DiscoveryError(f"unknown Steam account: {account_id}")
    if slot not in (1, 2, 3):
        raise DiscoveryError("slot must be 1, 2, or 3")
    selected_slot = next((item for item in account.slots if item.number == slot), None)
    if selected_slot is None:
        raise DiscoveryError(f"slot {slot} is not available for account {account_id}")
    return Selection(account=account, slot=selected_slot)

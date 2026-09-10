"""Normalize Steam achievements into character and unlock-method views."""

from __future__ import annotations

import re
from typing import Iterable, Mapping, Sequence

from .readers.steam_stats import AchievementDefinition


def _character(
    character_id: str,
    name_en: str,
    name_zh: str,
    sigil: str,
    *aliases: str,
    tainted: bool = False,
    unlock_title: str | None = None,
) -> dict[str, object]:
    return {
        "id": character_id,
        "name_en": name_en,
        "name_zh": name_zh,
        "sigil": sigil,
        "aliases": tuple({name_en.lower(), *(item.lower() for item in aliases)}),
        "tainted": tainted,
        "unlock_title": (unlock_title or name_en).lower(),
    }


CHARACTERS = (
    _character("isaac", "Isaac", "以撒", "I"),
    _character("magdalene", "Magdalene", "抹大拉", "M", "Maggy"),
    _character("cain", "Cain", "该隐", "C"),
    _character("judas", "Judas", "犹大", "J"),
    _character("blue_baby", "???", "???", "?", "Blue Baby"),
    _character("eve", "Eve", "夏娃", "E"),
    _character("samson", "Samson", "参孙", "S"),
    _character("azazel", "Azazel", "阿撒泻勒", "A"),
    _character("lazarus", "Lazarus", "拉撒路", "L"),
    _character("eden", "Eden", "伊甸", "E"),
    _character("lost", "The Lost", "游魂", "L", "Lost"),
    _character("lilith", "Lilith", "莉莉丝", "L"),
    _character("keeper", "Keeper", "店主", "K", "The Keeper"),
    _character("apollyon", "Apollyon", "亚玻伦", "A"),
    _character("forgotten", "The Forgotten", "遗骸", "F", "Forgotten"),
    _character("bethany", "Bethany", "伯大尼", "B"),
    _character("jacob_esau", "Jacob & Esau", "雅各与以扫", "J+E", "Jacob and Esau"),
    _character("tainted_isaac", "Tainted Isaac", "里以撒", "I′", tainted=True, unlock_title="The Broken"),
    _character("tainted_magdalene", "Tainted Magdalene", "里抹大拉", "M′", "Tainted Maggy", tainted=True, unlock_title="The Dauntless"),
    _character("tainted_cain", "Tainted Cain", "里该隐", "C′", tainted=True, unlock_title="The Hoarder"),
    _character("tainted_judas", "Tainted Judas", "里犹大", "J′", tainted=True, unlock_title="The Deceiver"),
    _character("tainted_blue_baby", "Tainted ???", "里???", "?′", "Tainted Blue Baby", tainted=True, unlock_title="The Soiled"),
    _character("tainted_eve", "Tainted Eve", "里夏娃", "E′", tainted=True, unlock_title="The Curdled"),
    _character("tainted_samson", "Tainted Samson", "里参孙", "S′", tainted=True, unlock_title="The Savage"),
    _character("tainted_azazel", "Tainted Azazel", "里阿撒泻勒", "A′", tainted=True, unlock_title="The Benighted"),
    _character("tainted_lazarus", "Tainted Lazarus", "里拉撒路", "L′", tainted=True, unlock_title="The Enigma"),
    _character("tainted_eden", "Tainted Eden", "里伊甸", "E′", tainted=True, unlock_title="The Capricious"),
    _character("tainted_lost", "Tainted Lost", "里游魂", "L′", "Tainted The Lost", tainted=True, unlock_title="The Baleful"),
    _character("tainted_lilith", "Tainted Lilith", "里莉莉丝", "L′", tainted=True, unlock_title="The Harlot"),
    _character("tainted_keeper", "Tainted Keeper", "里店主", "K′", tainted=True, unlock_title="The Miser"),
    _character("tainted_apollyon", "Tainted Apollyon", "里亚玻伦", "A′", tainted=True, unlock_title="The Empty"),
    _character("tainted_forgotten", "Tainted Forgotten", "里遗骸", "F′", "Tainted The Forgotten", tainted=True, unlock_title="The Fettered"),
    _character("tainted_bethany", "Tainted Bethany", "里伯大尼", "B′", tainted=True, unlock_title="The Zealot"),
    _character("tainted_jacob", "Tainted Jacob", "里雅各", "J′", tainted=True, unlock_title="The Deserter"),
)


CATEGORY_DEFINITIONS = {
    "character": {"name_zh": "角色", "description": "角色通关、角色解锁与初始状态"},
    "challenge": {"name_zh": "挑战", "description": "编号挑战及其奖励"},
    "route_boss": {"name_zh": "流程与 Boss", "description": "章节、路线、结局与 Boss 击杀"},
    "collection": {"name_zh": "收集与累计", "description": "收集、捐款、击杀和长期累计"},
    "special_run": {"name_zh": "单局特殊", "description": "无伤、连胜、限时和单局行为"},
    "daily_online": {"name_zh": "每日与联机", "description": "每日挑战、周期和联机目标"},
    "milestone": {"name_zh": "综合里程碑", "description": "全收集与总体完成目标"},
    "other": {"name_zh": "其他", "description": "尚未归入主要解锁方式的成就"},
}


def _contains(text: str, *phrases: str) -> bool:
    return any(phrase in text for phrase in phrases)


def extract_character_relations(
    condition_zh: str,
    condition_en: str,
    name_en: str = "",
    description_en: str = "",
) -> list[dict[str, str]]:
    """Extract character relationships from retained achievement metadata."""

    condition_text = condition_en.casefold()
    name_lower = name_en.casefold().strip()
    description_text = description_en.casefold()
    chinese_text = re.sub(
        r"\{\{[^{}|]+\|([^{}]+)\}\}",
        lambda match: match.group(1).split("|")[-1].strip(),
        condition_zh,
    )
    relations: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    unlocking = _contains(
        description_text, "unlock a new character", "unlocked a new character"
    )

    def add(character_id: str, relation_type: str) -> None:
        key = (character_id, relation_type)
        if key not in seen:
            seen.add(key)
            relations.append({"id": character_id, "relation": relation_type})

    all_characters = _contains(condition_text, "all characters", "every character") or _contains(
        chinese_text, "所有角色", "全部角色"
    )
    all_normal = "all non-tainted characters" in condition_text or _contains(
        chinese_text, "所有非堕化角色", "所有表角色"
    )
    for character in CHARACTERS:
        aliases = character["aliases"]
        if unlocking and name_lower == character["unlock_title"]:
            add(str(character["id"]), "unlocks_character")
        if (all_characters or (all_normal and not character["tainted"])):
            add(str(character["id"]), "related_character")
        elif any(
            re.search(rf"\b(?:as|with)\s+{re.escape(alias)}(?!\w)", condition_text)
            for alias in aliases
        ):
            add(str(character["id"]), "required_character")
        name_zh = str(character["name_zh"])
        if re.search(rf"(?:用|使用|作为|操纵)\s*{re.escape(name_zh)}", chinese_text):
            add(str(character["id"]), "required_character")
        if any(
            re.search(
                rf"\b{re.escape(alias)}\s+(?:now\s+)?(?:holds|starts with)",
                description_text,
            )
            for alias in aliases
        ):
            add(str(character["id"]), "starting_item_for_character")
    return relations


def classify_achievement(
    values: Mapping[str, object],
    relations: Sequence[Mapping[str, str]],
) -> list[str]:
    text = " ".join(str(value) for value in values.values() if value).casefold()
    result: list[str] = []
    if relations:
        result.append("character")
    if re.search(r"\bchallenge\s*#?\d+", text):
        result.append("challenge")
    if _contains(
        text, "defeat ", "beat ", "complete the ", "kill ", "killed ",
        "mom's heart", "boss rush", "the chest", "the dark room", "the void",
        "mother", "mega satan", "delirium", "the beast", "hush",
    ):
        result.append("route_boss")
    if _contains(
        text, "collect ", "pick up ", "donate ", "donation machine", "items and secrets",
        "kill 100", "destroy 100", "make 100", "use 100", "complete the bestiary",
        "become guppy", "become beelzebub", "add both ", "to your collection",
    ) or re.search(
        r"\b(?:visit|destroy|die|use|blow up|play|take|recharge|purchase|acquire|open|sleep in|spend)\b.*\b\d+",
        text,
    ):
        result.append("collection")
    if _contains(
        text, "without taking damage", "in one run", "in a row", "win 5",
        "within 20 minutes", "within 30 minutes", "without picking up", "win streak",
        "victory lap", "in a run", "in a single", "same room", "only half a heart",
        "times larger than",
    ):
        result.append("special_run")
    if _contains(text, "daily challenge", "daily run", "online", "co-op", "cooperative"):
        result.append("daily_online")
    if _contains(
        text, "unlock all", "platinum god", "real platinum god", "dead god",
        "1001%", "1000000%", "infinity%",
    ):
        result.append("milestone")
    return result or ["other"]


def build_catalog(
    definitions: Iterable[AchievementDefinition],
    overrides: Mapping[int, Mapping[str, object]] | None = None,
) -> list[dict[str, object]]:
    """Build serializable catalog entries from the local Steam schema."""

    catalog: list[dict[str, object]] = []
    overrides = overrides or {}
    for definition in definitions:
        override = overrides.get(definition.id, {})
        unlock_condition = str(override.get("unlock_condition_en", ""))
        relations = extract_character_relations(
            "",
            unlock_condition or definition.description,
            definition.name,
            definition.description,
        )
        sources: list[dict[str, object]] = [{
            "type": "steam_schema",
            "group": definition.group,
            "bit": definition.bit,
        }]
        if override.get("url"):
            sources.append({"type": "wiki_gg", "url": str(override["url"])})
        catalog.append({
            "id": definition.id,
            "name_en": definition.name,
            "name_zh": definition.name,
            "description": definition.description,
            "unlock_condition_en": unlock_condition or definition.description,
            "unlock_condition_zh": unlock_condition or definition.description,
            "categories": classify_achievement(
                {
                    "name_en": definition.name,
                    "steam_description_en": definition.description,
                    "unlock_condition_en": unlock_condition,
                },
                relations,
            ),
            "character_relations": [
                {"character_id": relation["id"], "type": relation["relation"]}
                for relation in relations
            ],
            "icon": definition.icon,
            "icon_locked": definition.icon_locked,
            "status": "unknown",
            "sources": sources,
        })
    catalog.sort(key=lambda item: int(item["id"]))
    return catalog

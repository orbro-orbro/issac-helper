# Isaac Helper MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a complete local-browser MVP that reads Isaac Steam achievements and Repentance+ Secrets, saves private local snapshots, and presents character, category, and full-achievement views.

**Architecture:** A dependency-free Python package owns discovery, binary parsing, catalog normalization, snapshots, and a loopback-only HTTP API. A vanilla HTML/CSS/JavaScript client consumes that API. Personal files are only read in place and generated snapshots stay under the ignored `data/profiles/` directory.

**Tech Stack:** Python 3.12 standard library, `unittest`, HTML5, CSS, vanilla JavaScript, PowerShell.

**Spec:** `docs/superpowers/specs/2026-09-09-isaac-achievement-helper-design.md`

## Global Constraints

- Bind the service only to `127.0.0.1`.
- Do not modify, restore, move, or delete Steam or game saves.
- Do not accept arbitrary filesystem paths through HTTP.
- Keep Steam account identifiers, source paths, raw saves, and snapshots out of tracked files.
- Use no runtime third-party dependencies and no frontend build step.
- Treat Steam achievement bits and game-save Secret flags as separate states.
- Unknown or truncated binary formats must fail with a clear error instead of guessed offsets.
- The interface is black, concise, responsive, keyboard-accessible, and respects reduced motion.

---

### Task 1: Binary KeyValues and Repentance+ readers

**Files:**
- Create: `app/__init__.py`
- Create: `app/readers/__init__.py`
- Create: `app/readers/binary_kv.py`
- Create: `app/readers/isaac_save.py`
- Test: `tests/test_binary_kv.py`
- Test: `tests/test_isaac_save.py`

**Interfaces:**
- Produces: `parse_binary_keyvalues(data: bytes) -> dict[str, object]`
- Produces: `read_binary_keyvalues(path: Path) -> dict[str, object]`
- Produces: `parse_secrets(data: bytes) -> SaveSecrets`
- Produces: `read_secrets(path: Path) -> SaveSecrets`
- `SaveSecrets` contains `format_name`, `secret_count`, and `unlocked_ids`.

- [ ] **Step 1: Write failing Binary KeyValues tests**

```python
def test_parses_nested_strings_ints_and_uint64():
    payload = obj("root", string("name", "Isaac") + integer("data", -1) + uint64("time", 7))
    assert parse_binary_keyvalues(payload) == {
        "root": {"name": "Isaac", "data": -1, "time": 7}
    }

def test_rejects_truncated_string():
    with self.assertRaisesRegex(BinaryKVError, "unterminated"):
        parse_binary_keyvalues(b"\x01root")
```

- [ ] **Step 2: Run `python -m unittest tests.test_binary_kv -v` and confirm missing-module failure**
- [ ] **Step 3: Implement the documented Valve Binary KeyValues types 0, 1, 2, 3, 5, 6, 7, 8, and 10 with offset-aware errors**
- [ ] **Step 4: Run the Binary KeyValues tests and confirm they pass**
- [ ] **Step 5: Write failing Repentance+ save tests**

```python
def test_reads_only_nonzero_secret_flags():
    data = bytearray(36)
    data[:14] = b"ISAACNGSAVE09R"
    data[24:28] = (4).to_bytes(4, "little")
    data[32:36] = bytes([1, 0, 2, 0])
    result = parse_secrets(bytes(data))
    assert result.secret_count == 4
    assert result.unlocked_ids == frozenset({1, 3})

def test_rejects_truncated_secret_table():
    with self.assertRaisesRegex(IsaacSaveError, "truncated"):
        parse_secrets(b"ISAACNGSAVE09R" + bytes(20))
```

- [ ] **Step 6: Run `python -m unittest tests.test_isaac_save -v` and confirm missing-function failure**
- [ ] **Step 7: Implement header validation, count-at-24, flags-at-32, and exact-length checks**
- [ ] **Step 8: Run both reader test modules and confirm they pass**

### Task 2: Steam schema/cache extraction and catalog classification

**Files:**
- Create: `app/readers/steam_stats.py`
- Create: `app/catalog.py`
- Test: `tests/test_steam_stats.py`
- Test: `tests/test_catalog.py`

**Interfaces:**
- Produces: `extract_schema(root: Mapping[str, object], app_id: str = "250900") -> list[AchievementDefinition]`
- Produces: `extract_unlocked(root: Mapping[str, object], definitions: Sequence[AchievementDefinition]) -> dict[int, datetime | None]`
- Produces: `build_catalog(definitions) -> list[dict[str, object]]`
- Every catalog item has `id`, `name_en`, `name_zh`, `description`, `categories`, `character_relations`, `status`, and source metadata.

- [ ] **Step 1: Write failing extraction tests using literal schema/cache dictionaries**

```python
def test_maps_unsigned_cache_bits_to_schema_ids():
    defs = extract_schema(schema_with_bits({0: "1", 31: "99"}))
    unlocked = extract_unlocked(cache_with_data(-2147483647), defs)
    assert set(unlocked) == {1, 99}

def test_uses_achievement_times_when_present():
    unlocked = extract_unlocked(cache_with_time(bit=2, timestamp=1_700_000_000), definitions())
    assert unlocked[3].timestamp() == 1_700_000_000
```

- [ ] **Step 2: Run `python -m unittest tests.test_steam_stats -v` and confirm failure**
- [ ] **Step 3: Implement schema traversal, unsigned 32-bit masks, and UTC timestamp conversion**
- [ ] **Step 4: Run Steam extraction tests and confirm they pass**
- [ ] **Step 5: Write failing catalog tests for character, challenge, boss/route, collection, special-run, daily/online, and milestone classification**

```python
def test_character_condition_has_explicit_relation():
    item = build_catalog([achievement(1, "Complete the Chest with Isaac.")])[0]
    assert "character" in item["categories"]
    assert item["character_relations"] == [
        {"character_id": "isaac", "type": "required_character"}
    ]

def test_every_achievement_has_at_least_one_category():
    assert all(item["categories"] for item in build_catalog(sample_definitions()))
```

- [ ] **Step 6: Run `python -m unittest tests.test_catalog -v` and confirm failure**
- [ ] **Step 7: Implement the 34-character registry, explicit aliases, layered classification rules, Chinese fallback labels, and stable sorting**
- [ ] **Step 8: Run all Task 2 tests and confirm they pass**

### Task 3: Safe discovery, snapshot generation, and history

**Files:**
- Create: `app/discovery.py`
- Create: `app/snapshots.py`
- Test: `tests/test_discovery.py`
- Test: `tests/test_snapshots.py`

**Interfaces:**
- Produces: `discover_accounts(steam_roots: Sequence[Path] | None = None) -> list[AccountInfo]`
- Produces: `resolve_selection(account_id: str, slot: int, accounts: Sequence[AccountInfo]) -> Selection`
- Produces: `build_snapshot(selection: Selection, output_root: Path) -> dict[str, object]`
- Produces: `load_snapshot(output_root: Path, account_id: str, slot: int) -> dict[str, object] | None`
- Snapshots contain Steam state, Secret state, summary, source timestamps/hashes, and sync differences.

- [ ] **Step 1: Write failing discovery tests around a temporary fake Steam tree and `savedatapath.txt`**
- [ ] **Step 2: Verify discovery tests fail because the module is absent**
- [ ] **Step 3: Implement registry/known-root discovery, numeric account validation, slot 1–3 enumeration, and newest-file metadata**
- [ ] **Step 4: Verify discovery tests pass**
- [ ] **Step 5: Write failing snapshot tests proving invalid accounts/slots are rejected, failed writes preserve the prior snapshot, and differences are calculated independently**
- [ ] **Step 6: Verify snapshot tests fail for the intended missing behavior**
- [ ] **Step 7: Implement SHA-256 source records, catalog merge, atomic `os.replace`, timestamped history, and state loading**
- [ ] **Step 8: Run Task 3 tests and confirm they pass**

### Task 4: Loopback HTTP service and startup

**Files:**
- Create: `app/server.py`
- Create: `start.ps1`
- Test: `tests/test_server.py`

**Interfaces:**
- Produces: `create_server(host="127.0.0.1", port=0, project_root=None) -> ThreadingHTTPServer`
- Routes: `GET /api/accounts`, `GET /api/catalog`, `GET /api/state`, `POST /api/update`, plus static files under `web/`.

- [ ] **Step 1: Write failing HTTP tests against a real ephemeral loopback server**

```python
def test_rejects_update_with_unknown_account():
    status, body = request_json("POST", "/api/update", {"account_id": "other", "slot": 2})
    assert status == 400
    assert body["error"]["code"] == "invalid_selection"

def test_static_paths_cannot_escape_web_root():
    status, _ = request("GET", "/../AGENTS.md")
    assert status in {400, 404}
```

- [ ] **Step 2: Run server tests and confirm missing-server failure**
- [ ] **Step 3: Implement strict JSON request handling, route query validation, consistent error objects, no-cache API headers, and safe static serving**
- [ ] **Step 4: Run server tests and confirm they pass**
- [ ] **Step 5: Add `start.ps1` to validate Python, launch `python -m app.server --open`, and propagate Ctrl+C cleanly**

### Task 5: Character-first browser interface

**Files:**
- Create: `web/index.html`
- Create: `web/styles.css`
- Create: `web/app.js`
- Test: `tests/test_web_contract.py`

**Interfaces:**
- Consumes the four HTTP routes from Task 4.
- Produces hash-routed views `characters`, `categories`, `all`, and `character/<id>` plus an update dialog.

- [ ] **Step 1: Write failing web contract tests that load the real HTML and check accessible landmarks, navigation labels, dialog controls, stylesheet/script links, and a no-JavaScript instruction**
- [ ] **Step 2: Run `python -m unittest tests.test_web_contract -v` and confirm missing-file failure**
- [ ] **Step 3: Build semantic HTML with skip link, persistent top bar, status region, main view root, and native update dialog**
- [ ] **Step 4: Make web contract tests pass**
- [ ] **Step 5: Implement state loading, update flow, character grid, character detail, category cards, all-achievement search/filter, empty states, and recoverable errors in `app.js`**
- [ ] **Step 6: Implement the quiet black token system in CSS: bone-white type, dried-blood focus/accent, soul-blue sync state, precise spacing, two-column narrow-screen grid, and `prefers-reduced-motion`**
- [ ] **Step 7: Self-critique against the design brief and remove any decoration that does not encode status or navigation**

### Task 6: End-to-end verification and public documentation

**Files:**
- Modify: `README.md`
- Create: `tests/test_live_read.py`

**Interfaces:**
- The optional live test reads installed files but never writes outside `data/profiles/` and is skipped when Isaac is unavailable.

- [ ] **Step 1: Write a live-read smoke test that verifies schema count is plausible, IDs are unique, and local totals agree with direct reader output**
- [ ] **Step 2: Run the live smoke test against the installed game and diagnose any parser mismatch before changing code**
- [ ] **Step 3: Update README with exact startup, update, privacy, source, and troubleshooting instructions**
- [ ] **Step 4: Run `python -m unittest discover -s tests -v` and require zero failures**
- [ ] **Step 5: Start the server on an ephemeral port, request `/`, `/api/accounts`, and `/api/catalog`, then stop it cleanly**
- [ ] **Step 6: Open the UI locally, capture a screenshot, review desktop and narrow-screen behavior, and fix only verified issues through failing tests where behavior is affected**

## Self-review

- Spec coverage: readers, discovery, snapshots, API, all four views, update dialog, categories, privacy, source separation, errors, accessibility, and local validation each map to a task.
- Placeholder scan: no `TODO`, `TBD`, or unspecified error-handling steps remain.
- Type consistency: account selection flows from `discover_accounts` through `resolve_selection` to `build_snapshot`; catalog dictionaries are the shared API payload for snapshot and UI.
- Scope decision: completion-mark decoding remains explicitly unavailable until the installed binary layout is verified; the UI reports this instead of guessing difficulty marks.

# Isaac Helper: Achievement Data Enhancement Design

**Date:** 2026-09-09  
**Status:** Approved in chat; awaiting written-spec review

## Goal

Replace the MVP's partial and heuristic achievement metadata with a unified, source-aware local catalog covering all 641 achievements in the installed game version. The browser remains fast and usable offline, while the user explicitly controls when source data is refreshed.

This phase improves achievement metadata only. Character completion marks, hard-mode marks, and intelligent run planning remain separate later phases.

## Scope

This phase includes:

- all 641 achievements from the installed Steam schema;
- Chinese and English names;
- Chinese unlock conditions and original Steam descriptions;
- unlock rewards and reward types;
- character relationships, including multiple characters where applicable;
- multi-label categories such as character, challenge, item, ending, and game mode;
- DLC or game-version metadata;
- verified Steam-to-Secret mapping state;
- locally cached achievement icons;
- field-level provenance and conflict records;
- a user-triggered catalog update flow;
- presentation of the enhanced data in existing character and category pages.

This phase excludes:

- character completion marks and hard-mode completion;
- an achievement dependency graph;
- intelligent run or route recommendations;
- favorites, notes, and history visualizations;
- automatic background updates.

## Chosen Approach

Use an offline generated catalog. A dedicated update pipeline reads the local Steam schema and fetches gameplay metadata from wiki.gg and Chinese terminology from the Huiji Wiki. It normalizes, merges, validates, and then atomically writes one runtime JSON catalog.

The web application never scrapes a wiki while rendering a page. It reads only the last valid local catalog, so a network outage or source-site change cannot prevent the application from starting.

Runtime unlock progress remains separate from reference metadata. The selected Steam account and save slot are joined to the catalog only when the application builds its API response.

## Architecture

### Source adapters

Each source is read through an independent adapter:

- **Local Steam schema adapter:** reads numeric IDs, schema group and bit coordinates, English names, Steam descriptions, and icon references.
- **wiki.gg adapter:** reads current unlock mechanics, rewards, character relationships, categories, and version details.
- **Huiji Wiki adapter:** adds Chinese names, established Chinese terminology, and Chinese explanations where available.

Failure in one network adapter does not discard data returned by other adapters. Local game and Steam files are always read-only.

### Normalization and merge

Adapters return source-specific records. A normalization layer converts them into a common intermediate shape, and a merge layer joins records by verified numeric achievement ID.

Source precedence is fixed:

1. The local Steam schema controls IDs, Steam-facing English metadata, and icon identity.
2. wiki.gg controls gameplay mechanics, rewards, relationships, and installed-version interpretation.
3. Huiji Wiki controls Chinese names and terminology.
4. If Huiji lacks an entry, the wiki.gg mechanic is translated clearly and marked as a translation rather than a verified Huiji value.

Conflicting values are never silently blended. The selected value follows the precedence above, while the conflicting alternatives and their sources are retained in the catalog's diagnostics.

### Validation and publication

The generated candidate catalog must pass structural validation before publication:

- exactly 641 unique achievement records;
- no duplicate numeric IDs or duplicate Steam group/bit coordinates;
- every required field is either populated or has an explicit missing reason;
- every achievement has an explicit Secret mapping state;
- categories and character references use known identifiers;
- referenced local icon files exist, or the record explicitly uses the fallback icon;
- provenance references identify a known source and source URL or local origin.

The updater writes the candidate to a temporary file in the project data directory, validates it, and then atomically replaces the active catalog. On any validation or write failure, it removes only the candidate file and leaves the previous active catalog untouched.

### Runtime catalog loader

The server loads the active catalog through one catalog module. Character pages, category pages, search, filters, and achievement details all consume the same normalized objects. Existing scattered front-end classification rules are removed once the catalog provides equivalent fields.

The user's Steam achievement state and selected save-slot Secret flags are joined by explicit identifiers. Steam and Secret states remain separate values. A disagreement is shown as a synchronization warning rather than resolved by guessing.

## Catalog Record

Each achievement record contains the following logical fields:

- `id`: canonical numeric achievement ID;
- `steam`: schema group, bit, numeric name, English name, description, and icon identity;
- `secret`: verified Secret ID and mapping status, or a documented reason for no mapping;
- `display`: Chinese name, English name, Chinese unlock condition, and original Steam description;
- `reward`: display name, reward type, and optional related internal ID;
- `characters`: zero or more stable character identifiers;
- `categories`: one or more stable category identifiers;
- `dlc`: DLC or game-version identifier;
- `icon`: local asset path and fallback state;
- `sources`: field-level provenance, retrieval date, source URL or local-file origin, and translation status;
- `conflicts`: non-selected conflicting claims retained for diagnostics;
- `missing`: explicit reasons for unavailable optional or expected fields.

User-specific fields such as unlocked state, save slot, account, and unlock timestamp are not stored in this catalog.

## Manual Update Flow

The existing update area gains two clearly separated actions:

- **Update personal progress:** reads the Steam account and save slot selected by the user and writes a local progress snapshot.
- **Update achievement data:** refreshes the shared reference catalog and icons without reading or changing personal progress.

The achievement-data update reports these stages:

1. read local Steam schema;
2. fetch wiki.gg;
3. fetch Huiji Wiki when available;
4. normalize and merge records;
5. download or reuse icon assets;
6. validate the candidate catalog;
7. publish the catalog and reload the browser data.

The final result shows the update time, achievement count, metadata completeness, warning count, and source failures. Application startup never triggers this flow automatically.

## Error Handling

- A total network failure keeps the previous catalog and produces a concise user-facing error.
- A Huiji-only failure may still publish if all structural rules pass; translated or retained Chinese fields are explicitly marked.
- A wiki page-layout change that produces incomplete or ambiguous records fails validation rather than replacing good data.
- A local Steam schema mismatch reports that the installed game data could not be reconciled and keeps the previous catalog.
- Icon download failures use a committed fallback icon and are counted as warnings.
- Detailed diagnostics are written to a local ignored log; the normal UI shows only a summary and offers details on demand.

## User Interface

The current concise black theme and overall navigation remain unchanged.

Achievement cards use the Chinese name and Chinese unlock condition as the primary content. The English name appears as secondary text. Reward, related characters, categories, DLC, and unlocked state are visible without exposing provenance noise.

Selecting an achievement opens its details with the full condition, reward, separate Steam and Secret states, unlock timestamp when available, version information, and compact source/conflict information.

Character and category pages query the catalog's multi-label fields. An achievement may therefore appear under multiple legitimate views without duplicated records or hard-coded front-end exceptions.

The update area shows separate last-update timestamps and status for personal progress and achievement data.

## Minimal Verification Strategy

Verification is intentionally limited to high-risk behavior:

- representative source parsing and normalized field mapping;
- merge precedence and conflict retention;
- catalog count, uniqueness, required-field, identifier, and asset validation;
- atomic publication and preservation of the previous catalog on failure;
- one server/web contract check proving the enhanced record is consumable by the browser.

There will not be one repetitive unit test per achievement, a broad visual-regression suite, or tests for simple static presentation. The catalog validator provides whole-dataset coverage without duplicating 641 nearly identical cases.

## Completion Criteria

The phase is complete when:

- the active local catalog contains exactly 641 unique achievements;
- every record has a verified Steam identity and an explicit Secret mapping state;
- Chinese name, condition, reward, category, and character relationship fields are present or carry an explicit missing reason;
- character, category, search, and detail views use the unified catalog;
- update failures cannot corrupt or replace the last valid catalog;
- the application remains usable offline after a successful catalog update;
- the update UI distinguishes personal progress from reference-data updates;
- no completion-mark or intelligent-planning behavior is introduced in this phase.

## Attribution

Generated records retain exact source links or local origins and retrieval dates. The project UI and documentation will provide attribution for wiki-derived content and preserve any source-specific attribution or licensing requirements that apply to redistributed text or images.

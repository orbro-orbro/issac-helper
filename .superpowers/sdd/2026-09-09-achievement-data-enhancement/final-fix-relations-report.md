# Final Fix Report — Character Achievement Relations

## Outcome

Restored the historical character relationship rules from base commit
`bc02f8795cf923954a6a2756e18ed0a849a6a86d` in the schema-v2 merge path.
The final commit uses message `fix: restore character achievement relations`;
its hash is reported in the final handoff because a commit cannot stably contain
its own hash.

## Root cause and repair

The schema-v2 extractor refactor retained condition-based
`required_character`/`related_character` detection, but stopped accepting the
Steam name and Steam description. The earlier implementation used those two
authoritative fields to derive `unlocks_character` and
`starting_item_for_character`, so both relation types disappeared from the
generated catalog.

`extract_character_relations()` now accepts those retained fields and applies
the previous name/description rules. Both `merge_catalog()` and the legacy
`build_catalog()` path supply the fields. Relations remain deduplicated,
multi-label, and ordered by the stable `CHARACTERS` registry.

## TDD and validation evidence

- RED: the new focused cases failed five assertions before the production
  repair: #1 and three other historical character unlock mappings were empty,
  and #29 lacked Isaac's starting-item relation.
- GREEN: `python -m unittest tests.test_catalog -v` passed all 7 tests after the
  repair.
- Whole-catalog validator: valid, 0 errors, 642 expected pre-existing
  warnings (641 unverified Secret mappings and one fallback icon).
- The 641-record baseline was recomputed offline from its retained display,
  Steam-description, and condition fields. A SHA-256 projection excluding only
  derived `characters` and `categories` was identical before and after:
  `521ed56e3119ec71843d61d57503211974c63cb26b79c6fc22c36fd329a23006`.
  Thus source values, provenance, timestamps, conflicts, missing markers,
  diagnostics, and icon metadata were preserved.

## Catalog counts

- Achievements: 641
- Achievements with character relations: 395
- Achievements categorized as `character`: 395
- Total relations: 481
- `required_character`: 381
- `related_character`: 85
- `unlocks_character`: 14
- `starting_item_for_character`: 1

Representative outcomes:

- Achievement #1: Magdalene / `unlocks_character`
- Achievement #29: Isaac / `starting_item_for_character` and Blue Baby /
  `required_character`

## Concerns

No new data-source or provenance concern was introduced. The restored behavior
intentionally matches the earlier rules: only Steam descriptions explicitly
stating that a new character was unlocked drive `unlocks_character`, and only
the retained Steam wording matching `holds` or `starts with` drives
`starting_item_for_character`. Existing catalog limitations outside this fix
(including unavailable Huiji fields and unverified Secret mappings) remain
unchanged.

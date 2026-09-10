# Final fix: wiki source-integrity guard

## Scope

- Added a pre-merge wiki.gg integrity gate in `app/catalog_update.py`.
- Added focused updater regressions in `tests/test_catalog_pipeline.py`.
- Did not modify the generated catalog, README, or unrelated implementation files.

## Root cause

The merged catalog uses Steam as the canonical record set, and the catalog validator permits sourced fields to be absent when the merge records a missing reason. As a result, an empty wiki parser result still produced the expected number of Steam-backed records and could replace a complete catalog with zero English unlock mechanics.

## Guard and rationale

The updater now validates wiki output immediately after fetching it, before Huiji fallback, icon caching, merging, or publication. Every returned row must be a `wiki_gg` `SourceAchievement` whose embedded ID matches its mapping key. At least 95% of the Steam canonical IDs must be present, and at least 95% of those expected IDs must have a nonblank string `unlock_condition_en`.

The checked-in active catalog has identity and usable English mechanics for 641/641 Steam IDs. The 95% floor permits a small source lag after a game release while rejecting empty, changed-layout, materially truncated, misidentified, or mechanics-free parser output. Huiji is not part of the invariant.

## TDD evidence

- RED: `python -m unittest tests.test_catalog_pipeline -v` failed five regression paths before the guard: empty first run plus empty, 90%-coverage, identity-mismatched, and mechanics-empty updates with a prior catalog.
- GREEN: the same command passed all 15 tests after the guard was added.

## Review notes

The requested no-subagent constraint prevented dispatching a separate code-review agent, so review was limited to the focused diff, mutation checks, and the required suite. The intentional operational tradeoff is fail-closed behavior when wiki coverage drops below 95%; the active catalog remains untouched and the structured update error reports the measured coverage.

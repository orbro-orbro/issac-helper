# Legacy progress snapshot compatibility

## Outcome

- Normalized schema-version-1 flat progress records and current nested `progress` records at the UI read boundary.
- Kept nested progress canonical when both shapes are present.
- Preserved independent Steam, Secret, unlock timestamp, and sync-warning values.
- Treats absent or non-boolean unlock state as unknown instead of confirmed locked.

## TDD evidence

- Red: `python -m unittest tests.test_web_contract -v` — 16 tests run, with the two expected legacy regressions failing (`flat unlocked` and `flat missing`).
- Green: `python -m unittest tests.test_web_contract -v` — 16 tests passed.
- The focused tests execute the production JavaScript with Node and skip only when the Node executable is unavailable.

## Scope and concerns

- Changed only `web/app.js`, `tests/test_web_contract.py`, and this report.
- No known compatibility concerns. Explicit `false` remains locked; missing state remains unknown.
- Commit hash is recorded in the final handoff because a commit cannot contain its own hash.

# Task 2 Report: Deterministic catalog merge and explicit classification

## Status

Complete. Commit: `1a15993 feat: merge achievement metadata with provenance`.

## Implementation

- Added `app.catalog_merge.choose_field()` with explicit candidate precedence, selected-value provenance, and conflicting-alternative retention.
- Added `app.catalog_merge.merge_catalog()` producing deterministic ID-sorted schema-v2 payloads with the required top-level payload keys and normalized achievement keys.
- Kept source responsibilities explicit: Steam metadata and English display name prefer Steam; wiki.gg supplies English mechanics/reward; Huiji supplies Chinese display/mechanics/reward terminology and DLC.
- Added field-level `sources`, per-record `conflicts`, and structured `missing` entries using `source_missing`.
- Added Secret mapping statuses. `verified` requires all three source records, a numeric Steam name equal to the merged ID, matching wiki/Huiji record IDs, and an ID within `1..secret_count`; mismatches are `conflict`, while missing/non-numeric/out-of-range evidence is `unverified`.
- Promoted deterministic public `extract_character_relations(condition_zh, condition_en)` and `classify_achievement(values, relations)` functions in `app.catalog`.
- Character extraction handles Chinese character text/templates and English `as/with <character>` phrases, deduplicating `(id, relation)` pairs.
- Classification retains multiple matching labels and falls back to `other` only when no specific rule matches.
- Migrated catalog tests to the normalized record shape, retaining the 34-character uniqueness test and one representative multi-label category test.

## RED

Command:

```text
python -m unittest tests.test_catalog_pipeline -v
```

Key output:

```text
ImportError: Failed to import test module: test_catalog_pipeline
ModuleNotFoundError: No module named 'app.catalog_merge'
FAILED (errors=1)
```

The failure was expected and specifically demonstrated that the new merge boundary did not yet exist.

After the first minimal implementation, the same command exposed a real relation-classification error: Chinese condition text incorrectly emitted extra `starting_item_for_character` relations. The expected `required_character` result failed, and the implementation was corrected before proceeding.

## GREEN

Command:

```text
python -m unittest tests.test_catalog_pipeline -v
```

Key output:

```text
Ran 2 tests in 0.007s
OK
```

Final required verification command:

```text
python -m unittest tests.test_catalog tests.test_catalog_pipeline -v
```

Key output:

```text
Ran 4 tests in 0.007s
OK
```

Diff hygiene command:

```text
git -c safe.directory='C:/Users/lenovo/Desktop/issac helper/.worktrees/achievement-data-v2' diff --check
```

Result: exit code 0; only Git's existing LF-to-CRLF conversion warnings were printed.

## Changed files

- `app/catalog.py`
- `app/catalog_merge.py`
- `tests/test_catalog.py`
- `tests/test_catalog_pipeline.py`

## Self-review

- Confirmed payload and per-achievement top-level keys match the brief exactly.
- Confirmed source candidate ordering is stable and achievement records are sorted numerically.
- Confirmed zero-valued Steam group/bit fields are retained rather than treated as missing.
- Confirmed conflicting source values do not overwrite the selected authoritative value and remain inspectable with source metadata.
- Confirmed character relations are deterministic and deduplicated, and every record receives at least one category.
- Confirmed Secret evidence ordering is deterministic (`steam_schema`, `wiki_gg`, `huiji` when all are present).
- Confirmed only the two requested test modules were used for final test verification.

## Concerns

None blocking. Git reports LF-to-CRLF conversion warnings for touched files due to the Windows checkout configuration; `git diff --check` remains clean.

## Fix round 1

Commit: `6deb4c6 fix: enforce canonical achievement identifiers`.

### Review findings addressed

- Canonical achievement records are now created only from Steam schema mapping keys. IDs found only in wiki.gg or Huiji are excluded from `achievements` and retained deterministically in `diagnostics.external_only_ids` with their contributing source names.
- English character alias matching now uses a negative word-character lookahead after the alias. This preserves normal word-name boundaries while correctly recognizing `???` and `Tainted ???` before punctuation.

### RED

Command:

```text
python -m unittest tests.test_catalog tests.test_catalog_pipeline -v
```

Key output before the fixes:

```text
test_question_mark_character_aliases_match_before_punctuation ... FAIL (2 subtests)
test_external_only_ids_are_diagnostic_not_canonical ... FAIL
Ran 6 tests in 0.009s
FAILED (failures=3)
```

The relation tests returned empty lists for both punctuated question-mark aliases. The merge test received a full canonical achievement record for wiki-only ID 999 instead of an empty `achievements` list.

### GREEN

The canonical-ID fix was first isolated with:

```text
python -m unittest tests.test_catalog_pipeline -v
Ran 3 tests in 0.006s
OK
```

The alias-boundary fix was then isolated with:

```text
python -m unittest tests.test_catalog -v
Ran 3 tests in 0.007s
OK
```

Final required verification:

```text
python -m unittest tests.test_catalog tests.test_catalog_pipeline -v
Ran 6 tests in 0.007s
OK
```

`git diff --check` exited successfully and printed only the Windows LF-to-CRLF conversion warnings. The changes did not require migration of existing public callers, so the full suite was not run, per the fix-round boundary.

### Files changed

- `app/catalog.py`
- `app/catalog_merge.py`
- `tests/test_catalog.py`
- `tests/test_catalog_pipeline.py`

### Self-review and concerns

- Confirmed canonical ordering now derives solely from Steam schema keys.
- Confirmed external-only IDs are sorted and source ordering is stable (`wiki_gg`, then `huiji`).
- Confirmed `???` and `Tainted ???` do not overlap because each still requires an explicit `as/with` phrase before its full alias.
- Confirmed both original pipeline tests and the representative category test remain green.
- No blocking concerns. The only diagnostic noise is the existing LF-to-CRLF warning.

## Fix round 1 takeover: grouped external-only diagnostics

### RED

The controller-updated regression test was run with:

```text
python -m unittest tests.test_catalog_pipeline.CatalogMergeTests.test_external_only_ids_are_diagnostic_not_canonical -v
```

It failed because `diagnostics.external_only_ids` was still a list of per-ID objects (`id` plus `sources`) rather than source-keyed integer arrays.

### GREEN

`app/catalog_merge.py` now derives the canonical ID set from Steam and emits deterministic grouped diagnostics:

```text
{"wiki_gg": [sorted external IDs], "huiji": [sorted external IDs]}
```

Verification commands:

```text
python -m unittest tests.test_catalog_pipeline.CatalogMergeTests.test_external_only_ids_are_diagnostic_not_canonical -v
Ran 1 test in 0.000s
OK

python -m unittest tests.test_catalog tests.test_catalog_pipeline -v
Ran 6 tests in 0.007s
OK
```

### Change and commit

- Changed only the external-only diagnostics shape; canonical achievement selection and all other merge behavior are unchanged.
- Commit: `fix: group external-only diagnostics by source` (new non-amended takeover commit).
- `git diff --check` passed; only the existing Windows LF-to-CRLF conversion warnings were reported.

# Vendored Apache Ossie validation sources

Pinned to upstream commit `c5cb931d72029dc523a5dd18d267f083403786f2`
(2026-10-14, `apache/ossie`). Do not edit either file: `tools/ossie.py`
imports `validate.py` and reads `ossie-schema.json` as-is.

To re-pin: download both files at the new commit, update this note, and
re-run `python3 -m pytest tests/test_ossie_validate.py -q`. Any upstream
behavior change must surface as a test failure here, never silently.

- `validate.py` — `validation/validate.py` (Apache-2.0, header intact)
- `ossie-schema.json` — `core-spec/ossie-schema.json`, spec `0.2.0.dev0`

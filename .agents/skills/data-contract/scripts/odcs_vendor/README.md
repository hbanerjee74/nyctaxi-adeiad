# Vendored Open Data Contract Standard schema

Never edit a file here. A re-pin replaces the file and updates this README in the same commit.

| | |
| --- | --- |
| Standard | Open Data Contract Standard (ODCS) |
| Standard version | `v3.2.0` |
| Upstream repository | https://github.com/bitol-io/open-data-contract-standard |
| Upstream path | `schema/odcs-json-schema-v3.2.0.json` |
| Pinned commit | `8b551607aad6801979bf4c209385e78fc4d029e5` |
| Bytes / sha256 | 110505 / `edb41f33ec46e847…` |

`odcs.py check` loads this file and nothing else: it never fetches, so a validation run is offline by construction.

The published standard takes precedence over this schema where the two disagree. `logicalTypeOptions` is
the case that proves it — the schema leaves it an open object, while the standard documents `timezone` and
`defaultTimezone` for it. `check` enforces the documented keys with its own allow-list rather than
trusting the schema to.

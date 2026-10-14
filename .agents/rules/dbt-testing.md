# dbt testing

## Generic tests (C1)

- Every primary key has `unique` and `not_null`.
- Every foreign key to a conformed dimension has `relationships`.
- A column with a closed set of values has `accepted_values`.

## Freshness (C2)

Declare source freshness where a source is loaded on a schedule. A source loaded as a one-off needs none.

## Singular tests (C4)

Live in `transformation/tests/`, named `assert_<what_must_hold>.sql`, and return the rows that violate the assertion.

## Unit tests (C5)

A model needs a unit test when its logic has a branch a reviewer could get wrong: ordering and tie-breaks, deduplication, and state classification. Today: `int_status_intervals`, `int_trips_enriched`, `int_trips_conformed`. Unit tests live in `_unit_tests.yml` beside the model.

Run data tests and unit tests as separate commands. The command for each layer is in `test-map.json`.

## Python tests

pytest tests live in `tests/`, run offline, and are mapped in `test-map.json`.

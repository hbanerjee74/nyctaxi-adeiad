"""Tests for tools/ossie.py validate (core + VIBEDATA second pass)."""

import json
import sys
from pathlib import Path

import yaml
from typer.testing import CliRunner

SKILL_SCRIPTS = Path(__file__).resolve().parent.parent / ".agents" / "skills" / "semantic-model" / "scripts"
sys.path.insert(0, str(SKILL_SCRIPTS))

from ossie import app  # noqa: E402

RUNNER = CliRunner()
CANONICAL = Path("logical-model/nyc_taxi_analytics.ossie.yaml")


def _doc():
    return yaml.safe_load(CANONICAL.read_text())


def _write(tmp_path, doc):
    target = tmp_path / "m.ossie.yaml"
    target.write_text(yaml.safe_dump(doc))
    return target


def _run(*args):
    result = RUNNER.invoke(app, list(args))
    assert result.exit_code in (0, 1, 2), result.output
    parsed = json.loads(result.stdout or "[]")  # stdout is always pure JSON
    return result.exit_code, parsed


def _codes(diags):
    return {(d.get("code"), d["severity"]) for d in diags}


def test_canonical_validates():
    """Structural gate only: the canonical model parses and resolves."""
    code, diags = _run("validate", str(CANONICAL))
    assert code == 0, diags
    assert not [d for d in diags if d["severity"] == "error"]
    assert ("vibedata/table-unjoined", "warning") in _codes(diags)


def test_missing_file_stdout_stays_json():
    code, diags = _run("validate", "nope_nonexistent.yaml")
    assert code == 1
    assert ("cli/unreadable", "error") in _codes(diags)


def test_empty_dir_stdout_stays_json(tmp_path):
    code, diags = _run("validate", str(tmp_path))
    assert code == 1
    assert ("cli/no-files", "error") in _codes(diags)


def test_dangling_alias_fails(tmp_path):
    doc = _doc()
    doc["custom_extensions"][0]["data"] = json.dumps({
        "vibedata_version": "1.0",
        "physical_tables": [{"name": "Ghost", "source": "core.x",
                             "table_type": "ALIAS", "alias_of": "Nope"}],
        "physical_joins": []})
    code, diags = _run("validate", str(_write(tmp_path, doc)))
    assert code == 1
    assert ("vibedata/alias-dangling", "error") in _codes(diags)


def test_self_alias_fails(tmp_path):
    doc = _doc()
    payload = json.loads(doc["custom_extensions"][0]["data"])
    payload["physical_tables"][3]["alias_of"] = "Pickup_Zone"
    doc["custom_extensions"][0]["data"] = json.dumps(payload)
    code, diags = _run("validate", str(_write(tmp_path, doc)))
    assert code == 1
    assert ("vibedata/alias-dangling", "error") in _codes(diags)


def test_dangling_lts_table_fails(tmp_path):
    doc = _doc()
    payload = json.loads(doc["datasets"][0]["custom_extensions"][0]["data"])
    payload["logical_sources"][0]["physical_table"] = "Nope"
    doc["datasets"][0]["custom_extensions"][0]["data"] = json.dumps(payload)
    code, diags = _run("validate", str(_write(tmp_path, doc)))
    assert code == 1
    assert ("vibedata/lts-dangling-table", "error") in _codes(diags)


def test_unknown_column_map_key_fails(tmp_path):
    doc = _doc()
    payload = json.loads(doc["datasets"][0]["custom_extensions"][0]["data"])
    payload["logical_sources"][0]["column_map"]["nope_col"] = "nope_col"
    doc["datasets"][0]["custom_extensions"][0]["data"] = json.dumps(payload)
    code, diags = _run("validate", str(_write(tmp_path, doc)))
    assert code == 1
    assert ("vibedata/lts-unknown-field", "error") in _codes(diags)


def test_unknown_vibedata_key_fails(tmp_path):
    doc = _doc()
    payload = json.loads(doc["datasets"][0]["custom_extensions"][0]["data"])
    payload["logicl_sources_typo"] = payload.pop("logical_sources")
    doc["datasets"][0]["custom_extensions"][0]["data"] = json.dumps(payload)
    code, diags = _run("validate", str(_write(tmp_path, doc)))
    assert code == 1
    assert ("vibedata/unknown-key", "error") in _codes(diags)


def test_bad_cardinality_fails(tmp_path):
    doc = _doc()
    payload = json.loads(doc["relationships"][0]["custom_extensions"][0]["data"])
    payload["cardinality"] = "sometimes"
    doc["relationships"][0]["custom_extensions"][0]["data"] = json.dumps(payload)
    code, diags = _run("validate", str(_write(tmp_path, doc)))
    assert code == 1
    assert ("vibedata/bad-cardinality", "error") in _codes(diags)


def test_bad_physical_join_fails(tmp_path):
    doc = _doc()
    payload = json.loads(doc["relationships"][0]["custom_extensions"][0]["data"])
    payload["physical_join"] = "nonexistent_join"
    doc["relationships"][0]["custom_extensions"][0]["data"] = json.dumps(payload)
    code, diags = _run("validate", str(_write(tmp_path, doc)))
    assert code == 1
    assert ("vibedata/join-dangling", "error") in _codes(diags)


def test_non_json_data_fails(tmp_path):
    doc = _doc()
    doc["datasets"][0]["custom_extensions"][0]["data"] = "{nope"
    code, diags = _run("validate", str(_write(tmp_path, doc)))
    assert code == 1
    assert ("vibedata/data-not-json", "error") in _codes(diags)


def test_malformed_shapes_do_not_crash(tmp_path):
    doc = _doc()
    payload = json.loads(doc["datasets"][2]["custom_extensions"][0]["data"])
    payload["hierarchies"] = ["not-a-dict"]
    payload["scd"] = "type2"
    payload["logical_sources"] = [{"name": "x"}]
    doc["datasets"][2]["custom_extensions"][0]["data"] = json.dumps(payload)
    code, diags = _run("validate", str(_write(tmp_path, doc)))
    assert code == 1
    codes = _codes(diags)
    assert ("vibedata/hierarchy-not-object", "error") in codes
    assert ("vibedata/scd-not-object", "error") in codes
    assert ("vibedata/lts-dangling-table", "error") in codes
    assert not any(d.get("code") == "cli/check-crashed" for d in diags)


def test_scd_bad_type_fails(tmp_path):
    doc = _doc()
    payload = json.loads(doc["datasets"][2]["custom_extensions"][0]["data"])
    payload["scd"]["type"] = 7
    doc["datasets"][2]["custom_extensions"][0]["data"] = json.dumps(payload)
    code, diags = _run("validate", str(_write(tmp_path, doc)))
    assert code == 1
    assert ("vibedata/scd-bad-type", "error") in _codes(diags)


def test_partitioned_by_shape(tmp_path):
    doc = _doc()
    payload = json.loads(doc["datasets"][0]["custom_extensions"][0]["data"])
    payload["partitioned_by"] = ["pickup_date"]
    doc["datasets"][0]["custom_extensions"][0]["data"] = json.dumps(payload)
    code, _ = _run("validate", str(_write(tmp_path, doc)))
    assert code == 0
    payload["partitioned_by"] = "pickup_date"
    doc["datasets"][0]["custom_extensions"][0]["data"] = json.dumps(payload)
    code, diags = _run("validate", str(_write(tmp_path, doc)))
    assert code == 1
    assert ("vibedata/bad-partitioned-by", "error") in _codes(diags)


def test_duplicate_dataset_fails_upstream(tmp_path):
    doc = _doc()
    doc["datasets"].append(dict(doc["datasets"][0]))
    code, diags = _run("validate", str(_write(tmp_path, doc)))
    assert code == 1
    assert any(d["severity"] == "error" and "Duplicate dataset" in d["message"]
               for d in diags)


def test_hierarchy_unknown_level_fails(tmp_path):
    doc = _doc()
    payload = json.loads(doc["datasets"][1]["custom_extensions"][0]["data"])
    payload["hierarchies"][0]["levels"].append({"name": "nope", "key": ["nope_level"]})
    doc["datasets"][1]["custom_extensions"][0]["data"] = json.dumps(payload)
    code, diags = _run("validate", str(_write(tmp_path, doc)))
    assert code == 1
    assert ("vibedata/hierarchy-unknown-field", "error") in _codes(diags)


def test_checker_keys_match_schema():
    """Skill checker allowlists and vibedata-schema.json agree."""
    import ossie_vibedata as v
    schema = json.loads((SKILL_SCRIPTS / "vibedata-schema.json").read_text())
    defs = schema["$defs"]
    pairs = [(v.MODEL_KEYS, "modelPayload"), (v.DATASET_KEYS, "datasetPayload"),
             (v.RELATIONSHIP_KEYS, "relationshipPayload"),
             (v.PHYSICAL_TABLE_KEYS, "physicalTable"),
             (v.PHYSICAL_JOIN_KEYS, "physicalJoin"), (v.LTS_KEYS, "logicalSource"),
             (v.HIERARCHY_KEYS, "hierarchy"), (v.SCD_KEYS, "scd"),
             (v.VARIABLE_KEYS, "variable"), (v.LEVEL_KEYS, "level"),
             (v.LEVEL_REF_KEYS, "levelRef"), (v.METRIC_KEYS, "metricPayload"),
             (v.TIME_SERIES_KEYS, "timeSeries"), (v.NESTED_KEYS, "nested")]
    for keys, ref in pairs:
        assert keys == set(defs[ref]["properties"]), ref


def test_version_consistent_and_present(tmp_path):
    doc = _doc()
    code, _ = _run("validate", str(_write(tmp_path, doc)))
    assert code == 0
    payload = json.loads(doc["datasets"][0]["custom_extensions"][0]["data"])
    payload["vibedata_version"] = "9.9"
    doc["datasets"][0]["custom_extensions"][0]["data"] = json.dumps(payload)
    code, diags = _run("validate", str(_write(tmp_path, doc)))
    assert code == 1
    assert ("vibedata/version-mismatch", "error") in _codes(diags)
    del payload["vibedata_version"]
    doc["datasets"][0]["custom_extensions"][0]["data"] = json.dumps(payload)
    code, diags = _run("validate", str(_write(tmp_path, doc)))
    assert code == 1
    assert ("vibedata/version-missing", "error") in _codes(diags)


def test_note_keys_accepted(tmp_path):
    doc = _doc()
    payload = json.loads(doc["datasets"][0]["custom_extensions"][0]["data"])
    payload["logical_sources"][1]["note"] = (
        "billable_revenue refused: agg sums unfiltered totals; content_filter held by "
        "assert_trip_sources_match_their_content_filter")
    doc["datasets"][0]["custom_extensions"][0]["data"] = json.dumps(payload)
    model_payload = json.loads(doc["custom_extensions"][0]["data"])
    model_payload["physical_tables"][0]["note"] = "detail grain base table"
    doc["custom_extensions"][0]["data"] = json.dumps(model_payload)
    code, diags = _run("validate", str(_write(tmp_path, doc)))
    assert code == 0
    assert not [d for d in diags if d["severity"] == "error"]


def test_from_column_unknown_fails(tmp_path):
    doc = _doc()
    doc["relationships"][0]["from_columns"] = ["no_such_field"]
    code, diags = _run("validate", str(_write(tmp_path, doc)))
    assert code == 1
    assert ("relationship/from-column-unknown", "error") in _codes(diags)


def test_crossdoc_diverged_dataset_fails(tmp_path):
    doc = _doc()
    twin = _doc()
    twin["name"] = "twin_model"
    twin["datasets"][1]["source"] = "core.dim_date_other"
    _write(tmp_path, doc)
    (tmp_path / "twin.ossie.yaml").write_text(yaml.safe_dump(twin))
    code, diags = _run("validate", str(tmp_path))
    assert code == 1
    assert ("crossdoc/diverged", "error") in _codes(diags)


def test_crossdoc_identical_copy_passes(tmp_path):
    doc = _doc()
    twin = _doc()
    twin["name"] = "twin_model"
    _write(tmp_path, doc)
    (tmp_path / "twin.ossie.yaml").write_text(yaml.safe_dump(twin))
    code, diags = _run("validate", str(tmp_path))
    assert code == 0, [d for d in diags if d["severity"] == "error"]


def test_crossdoc_diverged_metric_fails(tmp_path):
    doc = _doc()
    twin = _doc()
    twin["name"] = "twin_model"
    twin["metrics"][0]["expression"]["dialects"][0]["expression"] = "COUNT(*)"
    _write(tmp_path, doc)
    (tmp_path / "twin.ossie.yaml").write_text(yaml.safe_dump(twin))
    code, diags = _run("validate", str(tmp_path))
    assert code == 1
    assert ("crossdoc/diverged", "error") in _codes(diags)


def test_empty_column_map_tombstone_with_note_passes(tmp_path):
    doc = _doc()
    payload = json.loads(doc["datasets"][0]["custom_extensions"][0]["data"])
    payload["logical_sources"][1]["column_map"] = {}
    payload["logical_sources"][1]["note"] = (
        "withdrawn: agg built on the old billable rule; re-add when rebuilt")
    doc["datasets"][0]["custom_extensions"][0]["data"] = json.dumps(payload)
    code, diags = _run("validate", str(_write(tmp_path, doc)))
    assert code == 0, [d for d in diags if d["severity"] == "error"]


def test_crossdoc_identical_identity_with_local_roles_passes(tmp_path):
    """Copies must share identity; role-specific logical sources stay local."""
    doc = _doc()
    twin = _doc()
    twin["name"] = "twin_model"
    zone = json.loads(twin["datasets"][2]["custom_extensions"][0]["data"])
    zone["logical_sources"] = [s for s in zone["logical_sources"]
                               if "role" not in s["name"]]
    twin["datasets"][2]["custom_extensions"][0]["data"] = json.dumps(zone)
    _write(tmp_path, doc)
    (tmp_path / "twin.ossie.yaml").write_text(yaml.safe_dump(twin))
    code, diags = _run("validate", str(tmp_path))
    assert code == 0, [d for d in diags if d["severity"] == "error"]


def test_example_star_validates():
    example = SKILL_SCRIPTS.parent / "examples" / "star.ossie.yaml"
    code, diags = _run("validate", str(example))
    assert code == 0, [d for d in diags if d["severity"] == "error"]


def test_coverage_reports_unmapped(tmp_path):
    model = tmp_path / "model"
    marts = tmp_path / "marts"
    model.mkdir()
    marts.mkdir()
    _write(model, _doc())
    (marts / "fct_trip.sql").write_text("select 1")
    result = RUNNER.invoke(app, ["coverage", str(model), str(marts)])
    assert result.exit_code == 1
    codes = {d.get("code") for d in json.loads(result.stdout)}
    assert "coverage/phantom" in codes  # the sample doc names models absent from marts


def test_crossdoc_diverged_scd_fails(tmp_path):
    doc = _doc()
    twin = _doc()
    twin["name"] = "twin_model"
    zone = json.loads(twin["datasets"][2]["custom_extensions"][0]["data"])
    zone["scd"]["open_ended_value"] = "9999-12-31"
    twin["datasets"][2]["custom_extensions"][0]["data"] = json.dumps(zone)
    _write(tmp_path, doc)
    (tmp_path / "twin.ossie.yaml").write_text(yaml.safe_dump(twin))
    code, diags = _run("validate", str(tmp_path))
    assert code == 1
    assert ("crossdoc/diverged", "error") in _codes(diags)


def test_standalone_example_validates():
    example = SKILL_SCRIPTS.parent / "examples" / "standalone.ossie.yaml"
    code, diags = _run("validate", str(example))
    assert code == 0, [d for d in diags if d["severity"] == "error"]


def test_unmatched_file_in_model_dir_fails(tmp_path):
    _write(tmp_path, _doc())
    (tmp_path / "stray.ossie.yml").write_text("version: '0.2.0.dev0'\nname: x\n")
    code, diags = _run("validate", str(tmp_path))
    assert code == 1
    assert ("cli/unmatched-file", "error") in _codes(diags)


def test_to_column_unknown_fails(tmp_path):
    doc = _doc()
    doc["relationships"][0]["to_columns"] = ["not_a_field"]
    code, diags = _run("validate", str(_write(tmp_path, doc)))
    assert code == 1
    assert ("relationship/to-column-unknown", "error") in _codes(diags)


def test_primary_key_unknown_field_fails(tmp_path):
    doc = _doc()
    doc["datasets"][0]["primary_key"] = ["no_such_key"]
    code, diags = _run("validate", str(_write(tmp_path, doc)))
    assert code == 1
    assert ("vibedata/bad-key-column", "error") in _codes(diags)


def test_dataset_without_logical_source_fails(tmp_path):
    doc = _doc()
    payload = json.loads(doc["datasets"][1]["custom_extensions"][0]["data"])
    payload["logical_sources"] = []
    doc["datasets"][1]["custom_extensions"][0]["data"] = json.dumps(payload)
    code, diags = _run("validate", str(_write(tmp_path, doc)))
    assert code == 1
    assert ("vibedata/lts-empty", "error") in _codes(diags)


def test_suppliers_reports_unsupplied_metric(tmp_path):
    model = tmp_path / "model"
    model.mkdir()
    doc = _doc()
    payload = json.loads(doc["datasets"][0]["custom_extensions"][0]["data"])
    payload["logical_sources"][0]["column_map"].pop("fare_residual_total", None)
    doc["datasets"][0]["custom_extensions"][0]["data"] = json.dumps(payload)
    (model / "m.ossie.yaml").write_text(yaml.safe_dump(doc))
    result = RUNNER.invoke(app, ["suppliers", str(model)])
    assert result.exit_code == 1
    assert "suppliers/metric" in result.stdout


def _notes_doc(tmp_path, note):
    model = tmp_path / "model"
    model.mkdir()
    doc = _doc()
    for dataset in doc["datasets"]:
        payload = json.loads(dataset["custom_extensions"][0]["data"])
        for source in payload["logical_sources"]:
            source.pop("note", None)
        dataset["custom_extensions"][0]["data"] = json.dumps(payload)
    payload = json.loads(doc["datasets"][0]["custom_extensions"][0]["data"])
    payload["logical_sources"][0]["note"] = note
    doc["datasets"][0]["custom_extensions"][0]["data"] = json.dumps(payload)
    (model / "m.ossie.yaml").write_text(yaml.safe_dump(doc))
    return model


def test_notes_resolves_test_and_adr(tmp_path):
    model = _notes_doc(tmp_path, "reconciliation held by assert_ok, rule ADR 0003")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "assert_ok.sql").write_text("select 1")
    adrs = tmp_path / "adr"
    adrs.mkdir()
    (adrs / "0003-a.md").write_text("x")
    result = RUNNER.invoke(app, ["notes", str(model), str(tests), str(adrs)])
    assert result.exit_code == 0, result.stdout


def test_notes_flags_dangling_test(tmp_path):
    model = _notes_doc(tmp_path, "reconciliation held by assert_missing")
    tests = tmp_path / "tests"
    tests.mkdir()
    adrs = tmp_path / "adr"
    adrs.mkdir()
    result = RUNNER.invoke(app, ["notes", str(model), str(tests), str(adrs)])
    assert result.exit_code == 1
    assert "notes/dangling-test" in result.stdout


def test_notes_flags_dangling_adr(tmp_path):
    model = _notes_doc(tmp_path, "floored per ADR 9999")
    tests = tmp_path / "tests"
    tests.mkdir()
    adrs = tmp_path / "adr"
    adrs.mkdir()
    result = RUNNER.invoke(app, ["notes", str(model), str(tests), str(adrs)])
    assert result.exit_code == 1
    assert "notes/dangling-adr" in result.stdout


def test_notes_ignores_plain_prose(tmp_path):
    model = _notes_doc(tmp_path, "checked against the mart SQL and the seed ranges")
    tests = tmp_path / "tests"
    tests.mkdir()
    adrs = tmp_path / "adr"
    adrs.mkdir()
    result = RUNNER.invoke(app, ["notes", str(model), str(tests), str(adrs)])
    assert result.exit_code == 0, result.stdout


def test_where_key_is_now_unknown(tmp_path):
    """`where` was removed from the key set: a stale document fails loudly."""
    doc = _doc()
    payload = json.loads(doc["datasets"][0]["custom_extensions"][0]["data"])
    payload["logical_sources"][0]["where"] = "old style population prose"
    doc["datasets"][0]["custom_extensions"][0]["data"] = json.dumps(payload)
    code, diags = _run("validate", str(_write(tmp_path, doc)))
    assert code == 1
    assert ("vibedata/unknown-key", "error") in _codes(diags)


def test_notes_survives_malformed_payload(tmp_path):
    model = tmp_path / "model"
    model.mkdir()
    doc = _doc()
    doc["datasets"][0]["custom_extensions"][0]["data"] = '["not", "an", "object"]'
    (model / "m.ossie.yaml").write_text(yaml.safe_dump(doc))
    tests = tmp_path / "tests"
    tests.mkdir()
    adrs = tmp_path / "adr"
    adrs.mkdir()
    result = RUNNER.invoke(app, ["notes", str(model), str(tests), str(adrs)])
    assert result.exit_code in (0, 1)
    json.loads(result.stdout)  # stdout stays pure JSON


def _payload(node):
    return json.loads(node["custom_extensions"][0]["data"])


def _set_payload(node, payload):
    node["custom_extensions"][0]["data"] = json.dumps(payload)


def _named(items, name):
    return next(item for item in items if item["name"] == name)


def _trips_source(doc, source_name):
    trips = _named(doc["datasets"], "trips")
    payload = _payload(trips)
    return trips, payload, _named(payload["logical_sources"], source_name)


def test_hierarchy_level_needs_key(tmp_path):
    doc = _doc()
    date = _named(doc["datasets"], "date")
    payload = _payload(date)
    del payload["hierarchies"][0]["levels"][0]["key"]
    _set_payload(date, payload)
    code, diags = _run("validate", str(_write(tmp_path, doc)))
    assert code == 1
    assert ("vibedata/level-key-missing", "error") in _codes(diags)


def test_content_level_unknown_level_fails(tmp_path):
    doc = _doc()
    trips, payload, source = _trips_source(doc, "LTS2_zone_day_agg")
    source["content_levels"][0]["level"] = "fortnight"
    _set_payload(trips, payload)
    code, diags = _run("validate", str(_write(tmp_path, doc)))
    assert code == 1
    assert ("vibedata/level-ref-unknown-level", "error") in _codes(diags)


def test_content_level_must_start_at_its_dataset(tmp_path):
    doc = _doc()
    date = _named(doc["datasets"], "date")
    payload = _payload(date)
    payload["logical_sources"][0]["content_levels"] = [{"via": "trips_to_vendor"}]
    _set_payload(date, payload)
    code, diags = _run("validate", str(_write(tmp_path, doc)))
    assert code == 1
    assert ("vibedata/level-ref-wrong-dataset", "error") in _codes(diags)


def test_content_filter_unknown_field_fails(tmp_path):
    doc = _doc()
    trips, payload, source = _trips_source(doc, "LTS2_zone_day_agg")
    source["content_filter"] = "pickup_datetime >= :report_start"
    _set_payload(trips, payload)
    code, diags = _run("validate", str(_write(tmp_path, doc)))
    assert code == 1
    assert ("vibedata/content-filter-unknown-field", "error") in _codes(diags)


def test_content_filter_unknown_variable_fails(tmp_path):
    doc = _doc()
    trips, payload, source = _trips_source(doc, "LTS2_zone_day_agg")
    source["content_filter"] = "pickup_date >= :window_start"
    _set_payload(trips, payload)
    code, diags = _run("validate", str(_write(tmp_path, doc)))
    assert code == 1
    assert ("vibedata/content-filter-unknown-variable", "error") in _codes(diags)


def test_content_filter_literals_are_not_fields(tmp_path):
    doc = _doc()
    trips, payload, source = _trips_source(doc, "LTS2_zone_day_agg")
    source["content_filter"] = "airport_fee_status = 'not charged' AND pickup_date >= DATE '2024-01-01'"
    _set_payload(trips, payload)
    code, diags = _run("validate", str(_write(tmp_path, doc)))
    assert code == 0, diags


def test_content_filter_needs_a_holding_test(tmp_path):
    doc = _doc()
    trips, payload, source = _trips_source(doc, "LTS2_zone_day_agg")
    source["note"] = "checked by reading the SQL"
    _set_payload(trips, payload)
    code, diags = _run("validate", str(_write(tmp_path, doc)))
    assert code == 1
    assert ("vibedata/content-filter-unheld", "error") in _codes(diags)


def test_navigable_must_be_boolean(tmp_path):
    doc = _doc()
    trips, payload, source = _trips_source(doc, "LTS6_od_flow")
    source["navigable"] = "no"
    _set_payload(trips, payload)
    code, diags = _run("validate", str(_write(tmp_path, doc)))
    assert code == 1
    assert ("vibedata/bad-navigable", "error") in _codes(diags)


def test_metric_bad_aggregation_fails(tmp_path):
    doc = _doc()
    metric = _named(doc["metrics"], "trip_count")
    _set_payload(metric, {"vibedata_version": "1.2", "aggregation": "AVG"})
    code, diags = _run("validate", str(_write(tmp_path, doc)))
    assert code == 1
    assert ("vibedata/bad-aggregation", "error") in _codes(diags)


def test_metric_unknown_key_fails(tmp_path):
    doc = _doc()
    metric = _named(doc["metrics"], "trip_count")
    _set_payload(metric, {"vibedata_version": "1.2", "dimensionality": ["zone"]})
    code, diags = _run("validate", str(_write(tmp_path, doc)))
    assert code == 1
    assert ("vibedata/unknown-key", "error") in _codes(diags)


def test_metric_version_counts_toward_consistency(tmp_path):
    doc = _doc()
    metric = _named(doc["metrics"], "trip_count")
    _set_payload(metric, {"vibedata_version": "1.1", "aggregation": "SUM"})
    code, diags = _run("validate", str(_write(tmp_path, doc)))
    assert code == 1
    assert ("vibedata/version-mismatch", "error") in _codes(diags)


def test_level_based_metric_needs_a_hierarchy_level(tmp_path):
    doc = _doc()
    metric = _named(doc["metrics"], "billable_revenue_pickup_borough")
    payload = _payload(metric)
    payload["at_levels"] = [{"via": "trips_to_pickup_zone"}]
    _set_payload(metric, payload)
    code, diags = _run("validate", str(_write(tmp_path, doc)))
    assert code == 1
    assert ("vibedata/level-ref-needs-hierarchy", "error") in _codes(diags)


def test_time_series_expression_must_match_its_base(tmp_path):
    doc = _doc()
    metric = _named(doc["metrics"], "billable_revenue_prior_month")
    metric["expression"]["dialects"][0]["expression"] = "SUM(trips.total_amount)"
    code, diags = _run("validate", str(_write(tmp_path, doc)))
    assert code == 1
    assert ("vibedata/time-series-expression", "error") in _codes(diags)


def test_time_series_needs_a_time_hierarchy(tmp_path):
    doc = _doc()
    metric = _named(doc["metrics"], "billable_revenue_prior_month")
    payload = _payload(metric)
    payload["time_series"].update(
        {"via": "trips_to_pickup_zone", "hierarchy": "Geography", "level": "borough"})
    _set_payload(metric, payload)
    code, diags = _run("validate", str(_write(tmp_path, doc)))
    assert code == 1
    assert ("vibedata/time-series-not-time", "error") in _codes(diags)


def test_ago_needs_an_offset(tmp_path):
    doc = _doc()
    metric = _named(doc["metrics"], "billable_revenue_prior_month")
    payload = _payload(metric)
    del payload["time_series"]["offset"]
    _set_payload(metric, payload)
    code, diags = _run("validate", str(_write(tmp_path, doc)))
    assert code == 1
    assert ("vibedata/bad-time-series", "error") in _codes(diags)


FLEET = Path("logical-model/nyc_taxi_fleet.ossie.yaml")


def test_derived_metric_bound_to_a_column_fails(tmp_path):
    """A post-aggregation ratio read from an aggregate column re-sums ratios (ADR 0016)."""
    doc = yaml.safe_load(FLEET.read_text())
    shift = _named(doc["datasets"], "shift")
    payload = _payload(shift)
    _named(payload["logical_sources"], "LTS2_driver_day")["column_map"]["occupancy_rate"] = "occupancy_rate"
    _set_payload(shift, payload)
    code, diags = _run("validate", str(_write(tmp_path, doc)))
    assert code == 1
    assert ("vibedata/computed-metric-mapped", "error") in _codes(diags)


def test_derived_metric_unknown_input_fails(tmp_path):
    doc = yaml.safe_load(FLEET.read_text())
    metric = _named(doc["metrics"], "occupancy_rate")
    _set_payload(metric, {"vibedata_version": "1.2",
                          "derived_expression": "on_trip_hours / NULLIF(paid_hours, 0)"})
    code, diags = _run("validate", str(_write(tmp_path, doc)))
    assert code == 1
    assert ("vibedata/derived-unknown-metric", "error") in _codes(diags)


def test_suppliers_follow_derived_inputs(tmp_path):
    """A derived metric is supplied through its inputs; drop an input and it goes unsupplied."""
    model = tmp_path / "model"
    model.mkdir()
    doc = yaml.safe_load(FLEET.read_text())
    shift = _named(doc["datasets"], "shift")
    payload = _payload(shift)
    for source in payload["logical_sources"]:
        source["column_map"].pop("on_trip_hours", None)
    _set_payload(shift, payload)
    (model / "m.ossie.yaml").write_text(yaml.safe_dump(doc))
    result = RUNNER.invoke(app, ["suppliers", str(model)])
    assert result.exit_code == 1
    assert "on_trip_hours" in result.stdout
    assert "occupancy_rate" in result.stdout


def test_crossdoc_diverged_metric_payload_fails(tmp_path):
    model = tmp_path / "model"
    model.mkdir()
    doc = _doc()
    (model / "a.ossie.yaml").write_text(yaml.safe_dump(doc))
    twin = _doc()
    twin["name"] = "twin"
    _set_payload(_named(twin["metrics"], "trip_count"),
                 {"vibedata_version": "1.2", "aggregation": "MAX"})
    (model / "b.ossie.yaml").write_text(yaml.safe_dump(twin))
    code, diags = _run("validate", str(model))
    assert code == 1
    assert any(d["code"] == "crossdoc/diverged" and "metric 'trip_count'" in d["message"]
               for d in diags)


def test_model_variables_name_real_dbt_vars():
    """A content filter's :variable is only as good as the dbt var it is bound to."""
    project = yaml.safe_load(Path("transformation/dbt_project.yml").read_text())
    dbt_vars = set(project.get("vars") or {})
    for path in sorted(Path("logical-model").glob("*.ossie.yaml")):
        doc = yaml.safe_load(path.read_text())
        for variable in _payload(doc).get("variables", []):
            if "dbt_var" in variable:
                assert variable["dbt_var"] in dbt_vars, (path, variable)


def _nested(doc, name):
    metric = _named(doc["metrics"], name)
    return metric, _payload(metric)


def test_nested_expression_must_match_its_inner_metric(tmp_path):
    doc = _doc()
    metric = _named(doc["metrics"], "avg_daily_billable_revenue")
    metric["expression"]["dialects"][0]["expression"] = "SUM(trips.total_amount)"
    code, diags = _run("validate", str(_write(tmp_path, doc)))
    assert code == 1
    assert ("vibedata/nested-expression", "error") in _codes(diags)


def test_nested_last_needs_a_time_level(tmp_path):
    """LAST is a time balance: it needs one chronological level to order members by."""
    doc = yaml.safe_load(FLEET.read_text())
    metric, payload = _nested(doc, "closing_active_driver_count")
    payload["nested"]["over"] = [{"via": "shift_to_driver"}]
    _set_payload(metric, payload)
    code, diags = _run("validate", str(_write(tmp_path, doc)))
    assert code == 1
    assert ("vibedata/nested-order-not-time", "error") in _codes(diags)


def test_nested_bad_outer_fails(tmp_path):
    doc = _doc()
    metric, payload = _nested(doc, "avg_daily_billable_revenue")
    payload["nested"]["outer"] = "MODE"
    _set_payload(metric, payload)
    code, diags = _run("validate", str(_write(tmp_path, doc)))
    assert code == 1
    assert ("vibedata/bad-nested", "error") in _codes(diags)


def test_nested_calendar_members_need_a_hierarchy_level(tmp_path):
    """Calendar members come from a hierarchy level, so a bare relationship cannot supply them."""
    doc = yaml.safe_load(FLEET.read_text())
    metric, payload = _nested(doc, "mean_driver_occupancy_rate")
    payload["nested"]["empty_members"] = "calendar"
    _set_payload(metric, payload)
    code, diags = _run("validate", str(_write(tmp_path, doc)))
    assert code == 1
    assert ("vibedata/level-ref-needs-hierarchy", "error") in _codes(diags)


def test_metric_declares_one_computation(tmp_path):
    doc = _doc()
    metric, payload = _nested(doc, "avg_daily_billable_revenue")
    payload["time_series"] = {"function": "TODATE", "of": "billable_revenue",
                              "via": "trips_to_date", "hierarchy": "Time", "level": "month"}
    _set_payload(metric, payload)
    code, diags = _run("validate", str(_write(tmp_path, doc)))
    assert code == 1
    assert ("vibedata/metric-semantics-conflict", "error") in _codes(diags)


def test_nested_metric_bound_to_a_column_fails(tmp_path):
    doc = _doc()
    trips, payload, source = _trips_source(doc, "LTS7_daily_zone_revenue")
    source["column_map"]["avg_daily_billable_revenue"] = "total_revenue"
    _set_payload(trips, payload)
    code, diags = _run("validate", str(_write(tmp_path, doc)))
    assert code == 1
    assert ("vibedata/computed-metric-mapped", "error") in _codes(diags)


def test_metric_cycle_fails(tmp_path):
    doc = _doc()
    metric, payload = _nested(doc, "billable_average_fare")
    payload["derived_expression"] = "mean_pickup_zone_average_fare * 1.0"
    _set_payload(metric, payload)
    code, diags = _run("validate", str(_write(tmp_path, doc)))
    assert code == 1
    assert ("vibedata/metric-cycle", "error") in _codes(diags)


def test_suppliers_follow_nested_inputs(tmp_path):
    """A nested metric is supplied through the metric it nests."""
    model = tmp_path / "model"
    model.mkdir()
    doc = yaml.safe_load(FLEET.read_text())
    shift = _named(doc["datasets"], "shift")
    payload = _payload(shift)
    for source in payload["logical_sources"]:
        source["column_map"].pop("active_driver_count", None)
    _set_payload(shift, payload)
    (model / "m.ossie.yaml").write_text(yaml.safe_dump(doc))
    result = RUNNER.invoke(app, ["suppliers", str(model)])
    assert result.exit_code == 1
    assert "avg_daily_active_drivers" in result.stdout
    assert "closing_active_driver_count" in result.stdout

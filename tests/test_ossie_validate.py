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
    code, diags = _run("validate", str(CANONICAL))
    assert code == 0, diags
    assert not [d for d in diags if d["severity"] == "error"]
    assert ("vibedata/agg-metric-unverified", "warning") in _codes(diags)


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


def test_unmapped_field_fails(tmp_path):
    doc = _doc()
    payload = json.loads(doc["datasets"][0]["custom_extensions"][0]["data"])
    del payload["logical_sources"][0]["column_map"]["shift_id"]
    doc["datasets"][0]["custom_extensions"][0]["data"] = json.dumps(payload)
    code, diags = _run("validate", str(_write(tmp_path, doc)))
    assert code == 1
    assert ("vibedata/field-unmapped", "error") in _codes(diags)


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


def test_missing_payload_warns_only(tmp_path):
    doc = _doc()
    del doc["datasets"][4]["custom_extensions"]
    code, diags = _run("validate", str(_write(tmp_path, doc)))
    assert code == 0
    assert ("vibedata/no-payload", "warning") in _codes(diags)


def test_field_agg_only_fails(tmp_path):
    doc = _doc()
    payload = json.loads(doc["datasets"][0]["custom_extensions"][0]["data"])
    del payload["logical_sources"][0]["column_map"]["pickup_date"]
    doc["datasets"][0]["custom_extensions"][0]["data"] = json.dumps(payload)
    code, diags = _run("validate", str(_write(tmp_path, doc)))
    assert code == 1
    assert ("vibedata/field-agg-only", "error") in _codes(diags)


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
    payload["hierarchies"][0]["levels"].append("nope_level")
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
             (v.HIERARCHY_KEYS, "hierarchy"), (v.SCD_KEYS, "scd")]
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
    payload["logical_sources"][1]["note"] = "billable_revenue refused: agg sums unfiltered totals"
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


def test_empty_column_map_without_note_fails(tmp_path):
    doc = _doc()
    payload = json.loads(doc["datasets"][0]["custom_extensions"][0]["data"])
    payload["logical_sources"][1]["column_map"] = {}
    payload["logical_sources"][1].pop("note", None)
    doc["datasets"][0]["custom_extensions"][0]["data"] = json.dumps(payload)
    code, diags = _run("validate", str(_write(tmp_path, doc)))
    assert code == 1
    assert ("vibedata/empty-column-map", "error") in _codes(diags)


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


def test_columns_catches_phantom_column(tmp_path):
    model = tmp_path / "model"
    marts = tmp_path / "marts"
    model.mkdir()
    marts.mkdir()
    doc = _doc()
    payload = json.loads(doc["datasets"][0]["custom_extensions"][0]["data"])
    payload["logical_sources"][0]["column_map"]["shift_id"] = "no_such_column"
    doc["datasets"][0]["custom_extensions"][0]["data"] = json.dumps(payload)
    (model / "m.ossie.yaml").write_text(yaml.safe_dump(doc))
    (marts / "fct_trip.sql").write_text("select shift_id, trip_key from x")
    result = RUNNER.invoke(app, ["columns", str(model), str(marts)])
    assert result.exit_code == 1
    assert "columns/missing" in result.stdout


def test_columns_accepts_real_column(tmp_path):
    model = tmp_path / "model"
    marts = tmp_path / "marts"
    model.mkdir()
    marts.mkdir()
    doc = _doc()
    payload = json.loads(doc["datasets"][0]["custom_extensions"][0]["data"])
    payload["logical_sources"] = [payload["logical_sources"][0]]
    payload["logical_sources"][0]["column_map"] = {"shift_id": "shift_id"}
    doc["datasets"][0]["custom_extensions"][0]["data"] = json.dumps(payload)
    for dataset in doc["datasets"][1:]:
        dataset["custom_extensions"] = []
    (model / "m.ossie.yaml").write_text(yaml.safe_dump(doc))
    (marts / "fct_trip.sql").write_text("select shift_id from x")
    result = RUNNER.invoke(app, ["columns", str(model), str(marts)])
    assert result.exit_code == 0, result.stdout

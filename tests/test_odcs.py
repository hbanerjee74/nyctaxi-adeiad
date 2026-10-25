"""Tests for the data-contract tool (`.agents/skills/data-contract/scripts/odcs.py`)."""

import json
import sys
from pathlib import Path

import yaml
from typer.testing import CliRunner

SKILL_SCRIPTS = (
    Path(__file__).resolve().parent.parent / ".agents" / "skills" / "data-contract" / "scripts"
)
sys.path.insert(0, str(SKILL_SCRIPTS))

from odcs import app  # noqa: E402

RUNNER = CliRunner()


def _run(*args):
    """Invoke the CLI; stdout is always pure JSON."""
    result = RUNNER.invoke(app, list(args))
    assert result.exit_code in (0, 1, 2), result.output
    return result.exit_code, json.loads(result.stdout or "[]")


def _codes(diags):
    return [d["code"] for d in diags]


def _doc(table, **overrides):
    doc = {
        "apiVersion": "v3.2.0",
        "kind": "DataContract",
        "id": "c0ffee00-0000-4000-8000-000000000001",
        "name": table,
        "version": "1.0.0",
        "schema": [{"name": table, "dataGranularityDescription": "One row per event."}],
    }
    doc.update(overrides)
    return doc


def _repo(tmp_path, models=(), seeds=(), sources=None, logical_model=None):
    """A minimal repo: layers, seeds, a source's resource docs and a canonical model."""
    artifacts = {"data_contract": "contracts/{schema}/{table}.odcs.yaml"}
    if logical_model is not None:
        artifacts["logical_model"] = "logical-model/*.ossie.yaml"
        target = tmp_path / "logical-model" / "model.ossie.yaml"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(yaml.safe_dump(logical_model))
    repo_map = {
        "artifact_paths": artifacts,
        "layers": {
            "core": {"schema": "core", "path": "models/core/", "built_by": "dbt"},
            "seeds": {"schema": "seeds", "path": "seeds/", "built_by": "dbt"},
        },
        "sources": {},
    }
    for model in models:
        target = tmp_path / "models" / "core" / f"{model}.sql"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("select 1\n")
    for seed in seeds:
        target = tmp_path / "seeds" / f"{seed}.csv"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("a\n1\n")
    for name, (dataset, resources) in (sources or {}).items():
        docs = tmp_path / "ingestion" / "docs" / f"{name}.yml"
        docs.parent.mkdir(parents=True, exist_ok=True)
        docs.write_text(
            yaml.safe_dump(
                {"dataset": dataset, "resources": {r: {"description": r} for r in resources}}
            )
        )
        repo_map["sources"][name] = {
            "kind": "dlt",
            "dataset": dataset,
            "docs": f"ingestion/docs/{name}.yml",
        }
    (tmp_path / "repo-map.json").write_text(json.dumps(repo_map))
    return tmp_path


def _model(*datasets):
    """A canonical document naming one dataset per `(table, fields, primary_key)` tuple."""
    return {
        "version": "0.2.0.dev0",
        "name": "model",
        "datasets": [
            {
                "name": table,
                "source": f"core.{table}",
                "primary_key": list(primary_key),
                "fields": [
                    {"name": field, "datatype": datatype, "description": field}
                    for field, datatype in fields.items()
                ],
            }
            for table, fields, primary_key in datasets
        ],
        "relationships": [],
    }


def _element(table, *properties):
    return [{"name": table, "dataGranularityDescription": "One row per event.",
             "properties": list(properties)}]


def _prop(name, logical_type, **overrides):
    prop = {"name": name, "logicalType": logical_type}
    prop.update(overrides)
    return prop


def _contract(tmp_path, schema_name, table_name, **overrides):
    target = tmp_path / "contracts" / schema_name / f"{table_name}.odcs.yaml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(yaml.safe_dump(_doc(table_name, **overrides)))
    return target


def test_check_accepts_a_declared_relation_with_its_contract(tmp_path):
    _repo(tmp_path, models=["a_model"])
    _contract(tmp_path, "core", "a_model")
    assert _run("check", "--root", str(tmp_path)) == (0, [])


def test_check_requires_a_contract_for_every_declared_relation(tmp_path):
    """dbt models, seeds and documented dlt resources all count, from the map alone."""
    _repo(tmp_path, models=["a_model", "b_model"], seeds=["band"], sources={"src": ("raw", ["t"])})
    _contract(tmp_path, "core", "a_model")
    code, diags = _run("check", "--root", str(tmp_path))
    assert code == 1
    assert _codes(diags) == ["contract/missing", "contract/missing", "contract/missing"]
    assert any("core.b_model" in d["message"] for d in diags)
    assert any("seeds.band" in d["message"] for d in diags)
    assert any("raw.t" in d["message"] for d in diags)


def test_check_rejects_a_contract_naming_no_declared_relation(tmp_path):
    _repo(tmp_path, models=["a_model"])
    _contract(tmp_path, "core", "a_model")
    _contract(tmp_path, "core", "gone")
    code, diags = _run("check", "--root", str(tmp_path))
    assert (code, _codes(diags)) == (1, ["contract/orphan"])


def test_check_rejects_a_present_but_empty_section(tmp_path):
    """Absence is the only honest 'no promise'; an empty `servers` claims one."""
    _repo(tmp_path, models=["a_model"])
    _contract(tmp_path, "core", "a_model", servers=[])
    code, diags = _run("check", "--root", str(tmp_path))
    assert (code, _codes(diags)) == (1, ["contract/empty-section"])
    assert "servers" in diags[0]["message"]


def test_check_warns_but_passes_when_the_grain_is_unstated(tmp_path):
    """Onboarding may leave the grain to review; the gate warns, the review refuses."""
    _repo(tmp_path, models=["a_model"])
    _contract(tmp_path, "core", "a_model", schema=[{"name": "a_model"}])
    code, diags = _run("check", "--root", str(tmp_path))
    assert (code, _codes(diags)) == (0, ["contract/no-grain"])
    assert diags[0]["severity"] == "warning"


def test_check_says_so_when_the_map_declares_no_contract_path(tmp_path):
    """A repo that has not adopted contracts gets a diagnosis, not a traceback."""
    (tmp_path / "repo-map.json").write_text(json.dumps({"artifact_paths": {}, "layers": {}}))
    code, diags = _run("check", "--root", str(tmp_path))
    assert (code, _codes(diags)) == (1, ["contract/unconfigured"])


TRIP_FIELDS = {"trip_key": "String", "pickup_date": "Date", "total_amount": "Decimal"}


def _trips(tmp_path, fields=TRIP_FIELDS, primary_key=("trip_key",)):
    """A gold contract and the canonical document that declares the same relation."""
    _repo(tmp_path, models=["a_model"], logical_model=_model(("a_model", fields, primary_key)))
    return _contract(
        tmp_path,
        "core",
        "a_model",
        schema=_element(
            "a_model",
            _prop("trip_key", "string", primaryKey=True),
            _prop("pickup_date", "date"),
            _prop("total_amount", "number"),
        ),
    )


def test_gold_agreement_passes_when_the_contract_matches_the_model(tmp_path):
    _trips(tmp_path)
    assert _run("check", "--root", str(tmp_path)) == (0, [])


def test_gold_omission_fails_and_names_the_relation_and_field(tmp_path):
    """The contract carries less than the canonical document declares for that relation."""
    _contract(tmp_path, "core", "a_model", schema=_element(
        "a_model", _prop("trip_key", "string", primaryKey=True), _prop("total_amount", "number")))
    _repo(tmp_path, models=["a_model"], logical_model=_model(("a_model", TRIP_FIELDS, ["trip_key"])))
    code, diags = _run("check", "--root", str(tmp_path))
    assert (code, _codes(diags)) == (1, ["gold/omits-declared"])
    assert "core.a_model" in diags[0]["message"] and "pickup_date" in diags[0]["message"]


def test_gold_logical_type_disagreement_names_both_sides(tmp_path):
    """A `Decimal` reduces to `number`; a contract saying otherwise contradicts the model."""
    _trips(tmp_path)
    _contract(tmp_path, "core", "a_model", schema=_element(
        "a_model",
        _prop("trip_key", "string", primaryKey=True),
        _prop("pickup_date", "date"),
        _prop("total_amount", "string")))
    code, diags = _run("check", "--root", str(tmp_path))
    assert (code, _codes(diags)) == (1, ["gold/divergent"])
    assert "'number'" in diags[0]["message"] and "'string'" in diags[0]["message"]


def test_gold_datetimetz_needs_the_timezone_option(tmp_path):
    """`DateTimeTz` reduces to a timestamp that carries the timezone option, and only it does."""
    _trips(tmp_path)
    loaded_at = _element("a_model",
                         _prop("trip_key", "string", primaryKey=True),
                         _prop("pickup_date", "date"),
                         _prop("total_amount", "number"),
                         _prop("loaded_at", "timestamp"))
    _contract(tmp_path, "core", "a_model", schema=loaded_at)
    _repo(tmp_path, models=["a_model"], logical_model=_model(
        ("a_model", {**TRIP_FIELDS, "loaded_at": "DateTimeTz"}, ["trip_key"])))
    code, diags = _run("check", "--root", str(tmp_path))
    assert (code, _codes(diags)) == (1, ["gold/divergent"])
    assert "timezone" in diags[0]["message"]
    loaded_at[0]["properties"][-1]["logicalTypeOptions"] = {"timezone": True}
    _contract(tmp_path, "core", "a_model", schema=loaded_at)
    assert _run("check", "--root", str(tmp_path)) == (0, [])


def test_gold_datetime_must_not_carry_the_timezone_option(tmp_path):
    """`DateTime` reduces to a timezone-free timestamp; the option would claim an offset it lacks."""
    _trips(tmp_path)
    schema = _element("a_model",
                      _prop("trip_key", "string", primaryKey=True),
                      _prop("pickup_date", "date"),
                      _prop("total_amount", "number"),
                      _prop("loaded_at", "timestamp", logicalTypeOptions={"timezone": True}))
    _contract(tmp_path, "core", "a_model", schema=schema)
    _repo(tmp_path, models=["a_model"], logical_model=_model(
        ("a_model", {**TRIP_FIELDS, "loaded_at": "DateTime"}, ["trip_key"])))
    code, diags = _run("check", "--root", str(tmp_path))
    assert (code, _codes(diags)) == (1, ["gold/divergent"])
    assert "timezone" in diags[0]["message"]


def test_gold_contract_with_no_document_fails(tmp_path):
    """A gold relation the canonical model never names has no agreed shape at all."""
    _repo(tmp_path, models=["a_model", "b_model"],
          logical_model=_model(("a_model", TRIP_FIELDS, ["trip_key"])))
    _contract(tmp_path, "core", "a_model", schema=_element(
        "a_model", _prop("trip_key", "string", primaryKey=True),
        _prop("pickup_date", "date"), _prop("total_amount", "number")))
    _contract(tmp_path, "core", "b_model")
    code, diags = _run("check", "--root", str(tmp_path))
    assert (code, _codes(diags)) == (1, ["gold/undeclared"])
    assert "core.b_model" in diags[0]["message"]


def test_gold_ignores_a_property_the_model_does_not_declare(tmp_path):
    """The canonical model is curated: a contract may carry columns it never declares."""
    _trips(tmp_path)
    _contract(tmp_path, "core", "a_model", schema=_element(
        "a_model",
        _prop("trip_key", "string", primaryKey=True),
        _prop("pickup_date", "date"),
        _prop("total_amount", "number"),
        _prop("audit_note", "string")))
    assert _run("check", "--root", str(tmp_path)) == (0, [])


def test_no_canonical_model_means_no_gold_diagnostics(tmp_path):
    """Not adopting a canonical model is not a broken contract set, whatever the map says."""
    _repo(tmp_path, models=["a_model"])
    _contract(tmp_path, "core", "a_model")
    assert _run("check", "--root", str(tmp_path)) == (0, [])

    elsewhere = tmp_path / "absent"
    _repo(elsewhere, models=["a_model"])
    _contract(elsewhere, "core", "a_model")
    map_path = elsewhere / "repo-map.json"
    repo_map = json.loads(map_path.read_text())
    repo_map["artifact_paths"]["logical_model"] = "logical-model/*.ossie.yaml"
    map_path.write_text(json.dumps(repo_map))
    assert _run("check", "--root", str(elsewhere)) == (0, [])

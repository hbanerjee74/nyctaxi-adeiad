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
    """Invoke the CLI; stdout is always pure JSON, so a crash fails here instead of passing as []."""
    result = RUNNER.invoke(app, list(args))
    assert result.stdout.strip(), f"no JSON on stdout: {result.exception!r}"
    assert result.exit_code in (0, 1, 2), result.output
    return result.exit_code, json.loads(result.stdout)


def _generated(tmp_path):
    """Write the keys `generate` owns, for the fixtures whose subject is not staleness."""
    assert _run("generate", "--root", str(tmp_path)) == (0, [])


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


def _repo(tmp_path, models=(), seeds=(), sources=None, logical_model=None, files=None):
    """A minimal repo: layers, seeds, a source's resource docs and a canonical model.

    `files` writes hand-written properties files, as `{relative path: text or document}`.
    """
    artifacts = {
        "data_contract": "contracts/{schema}/{table}.odcs.yaml",
        "ingestion_root": "ingestion/",
    }
    if logical_model is not None:
        artifacts["logical_model"] = "logical-model/*.ossie.yaml"
        target = tmp_path / "logical-model" / "model.ossie.yaml"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(yaml.safe_dump(logical_model))
    repo_map = {
        "artifact_paths": artifacts,
        "layers": {
            "bronze": {"schema": "bronze", "path": "ingestion/", "built_by": "dlt"},
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
    for relative, content in (files or {}).items():
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content if isinstance(content, str) else yaml.safe_dump(content))
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


PHYSICAL_TYPES = {
    "string": "VARCHAR",
    "integer": "BIGINT",
    "number": "DECIMAL(10,2)",
    "boolean": "BOOLEAN",
    "date": "DATE",
    "time": "TIME",
    "timestamp": "TIMESTAMP",
}


def _prop(name, logical_type, **overrides):
    """A contract property; every one carries a `physicalType`, as `reverse` writes it."""
    prop = {"name": name, "logicalType": logical_type,
            "physicalType": PHYSICAL_TYPES.get(logical_type, "VARCHAR")}
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
    _generated(tmp_path)
    assert _run("check", "--root", str(tmp_path)) == (0, [])


def test_check_requires_a_contract_for_every_declared_relation(tmp_path):
    """dbt models, seeds and documented dlt resources all count, from the map alone."""
    _repo(tmp_path, models=["a_model", "b_model"], seeds=["band"], sources={"src": ("raw", ["t"])})
    _contract(tmp_path, "core", "a_model")
    _generated(tmp_path)
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
    _generated(tmp_path)
    code, diags = _run("check", "--root", str(tmp_path))
    assert (code, _codes(diags)) == (1, ["contract/orphan"])


def test_check_rejects_a_present_but_empty_section(tmp_path):
    """Absence is the only honest 'no promise'; an empty `servers` claims one."""
    _repo(tmp_path, models=["a_model"])
    _contract(tmp_path, "core", "a_model", servers=[])
    _generated(tmp_path)
    code, diags = _run("check", "--root", str(tmp_path))
    assert (code, _codes(diags)) == (1, ["contract/empty-section"])
    assert "servers" in diags[0]["message"]


def test_check_warns_but_passes_when_the_grain_is_unstated(tmp_path):
    """Onboarding may leave the grain to review; the gate warns, the review refuses."""
    _repo(tmp_path, models=["a_model"])
    _contract(tmp_path, "core", "a_model", schema=[{"name": "a_model"}])
    _generated(tmp_path)
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
    _generated(tmp_path)
    assert _run("check", "--root", str(tmp_path)) == (0, [])


def test_gold_omission_fails_and_names_the_relation_and_field(tmp_path):
    """The contract carries less than the canonical document declares for that relation."""
    _contract(tmp_path, "core", "a_model", schema=_element(
        "a_model", _prop("trip_key", "string", primaryKey=True), _prop("total_amount", "number")))
    _repo(tmp_path, models=["a_model"], logical_model=_model(("a_model", TRIP_FIELDS, ["trip_key"])))
    _generated(tmp_path)
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
    _generated(tmp_path)
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
    _generated(tmp_path)
    code, diags = _run("check", "--root", str(tmp_path))
    assert (code, _codes(diags)) == (1, ["gold/divergent"])
    assert "timezone" in diags[0]["message"]
    loaded_at[0]["properties"][-1]["logicalTypeOptions"] = {"timezone": True}
    _contract(tmp_path, "core", "a_model", schema=loaded_at)
    _generated(tmp_path)
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
    _generated(tmp_path)
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
    _generated(tmp_path)
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
    _generated(tmp_path)
    assert _run("check", "--root", str(tmp_path)) == (0, [])


def test_no_canonical_model_means_no_gold_diagnostics(tmp_path):
    """Not adopting a canonical model is not a broken contract set, whatever the map says."""
    _repo(tmp_path, models=["a_model"])
    _contract(tmp_path, "core", "a_model")
    _generated(tmp_path)
    assert _run("check", "--root", str(tmp_path)) == (0, [])

    elsewhere = tmp_path / "absent"
    _repo(elsewhere, models=["a_model"])
    _contract(elsewhere, "core", "a_model")
    map_path = elsewhere / "repo-map.json"
    repo_map = json.loads(map_path.read_text())
    repo_map["artifact_paths"]["logical_model"] = "logical-model/*.ossie.yaml"
    map_path.write_text(json.dumps(repo_map))
    _generated(elsewhere)
    assert _run("check", "--root", str(elsewhere)) == (0, [])


CORE_PROPERTIES = """version: 2

models:
  - name: a_model
    description: >
      Hand-written prose the generator must not touch.
    columns:
      - name: trip_key
        description: '{{ doc("trip_key") }}'
        tests: [unique, not_null]
      - name: total_amount
        description: The fare total, as billed.
"""

SEED_PROPERTIES = """version: 2

seeds:
  - name: band
    description: Fare banding.
    columns:
      - name: band_order
        tests: [unique, not_null]
"""

ZERO_INDENT_PROPERTIES = """version: 2
models:
- name: a_model
  columns:
  - name: trip_key
    description: kept
"""

MODEL_WITH_DATA_TESTS = """version: 2

models:
  - name: a_model
    columns:
      - name: trip_key
        data_tests: [unique, not_null]
"""

SEED_WITH_DATA_TYPE = """version: 2

seeds:
  - name: band
    columns:
      - name: band_order
        data_type: INTEGER
        data_tests: [unique]
"""


def _entries(path, section="models"):
    """A properties file's entries, by the name dbt resolves them with."""
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    return doc, {entry["name"]: entry for entry in doc[section]}


def _rule(metric, **overrides):
    rule = {"type": "library", "metric": metric, "mustBe": 0}
    rule.update(overrides)
    return rule


def test_generate_writes_the_contract_and_a_data_type_per_column(tmp_path):
    """The generator augments the hand-written file: dbt rejects a second entry for one model."""
    _repo(tmp_path, models=["a_model", "b_model"],
          files={"models/core/_core.yml": CORE_PROPERTIES})
    _contract(tmp_path, "core", "a_model", schema=_element(
        "a_model",
        _prop("trip_key", "string", physicalType="VARCHAR", primaryKey=True),
        _prop("total_amount", "number", physicalType="DECIMAL(10,2)")))
    _contract(tmp_path, "core", "b_model", schema=_element(
        "b_model", _prop("vendor_id", "integer", physicalType="BIGINT")))
    assert _run("generate", "--root", str(tmp_path)) == (0, [])

    doc, entries = _entries(tmp_path / "models" / "core" / "_core.yml")
    assert [entry["name"] for entry in doc["models"]] == ["a_model"]
    model = entries["a_model"]
    assert model["contract"] == {"enforced": True}
    assert model["description"] == "Hand-written prose the generator must not touch.\n"
    columns = {column["name"]: column for column in model["columns"]}
    assert columns["trip_key"]["data_type"] == "VARCHAR"
    assert columns["trip_key"]["description"] == '{{ doc("trip_key") }}'
    assert columns["trip_key"]["tests"] == ["unique", "not_null"]
    assert columns["total_amount"]["data_type"] == "DECIMAL(10,2)"
    assert columns["total_amount"]["description"] == "The fare total, as billed."

    generated = _entries(tmp_path / "models" / "core" / "_generated.yml")[1]
    assert generated["b_model"]["contract"] == {"enforced": True}
    assert generated["b_model"]["columns"] == [
        {"name": "vendor_id", "data_type": "BIGINT"}
    ]


def test_generate_adds_an_entry_for_a_column_the_file_lacks(tmp_path):
    """`contract: enforced` fails on an output column with no entry, so one is added."""
    _repo(tmp_path, models=["a_model"],
          files={"models/core/_core.yml": CORE_PROPERTIES})
    _contract(tmp_path, "core", "a_model", schema=_element(
        "a_model",
        _prop("trip_key", "string", physicalType="VARCHAR"),
        _prop("pickup_date", "date", physicalType="DATE")))
    assert _run("generate", "--root", str(tmp_path)) == (0, [])

    model = _entries(tmp_path / "models" / "core" / "_core.yml")[1]["a_model"]
    assert model["columns"][-1] == {"name": "pickup_date", "data_type": "DATE"}
    assert [column["name"] for column in model["columns"]] == [
        "trip_key", "total_amount", "pickup_date"
    ]


def test_generate_writes_data_tests_for_a_seed_and_no_contract(tmp_path):
    """A seed cannot carry a contract; its enforcement is the generated tests list."""
    _repo(tmp_path, seeds=["band"], files={"seeds/seeds.yml": SEED_PROPERTIES})
    _contract(tmp_path, "seeds", "band", schema=_element(
        "band",
        _prop("band_order", "integer", physicalType="INTEGER",
              quality=[_rule("duplicateValues")]),
        _prop("band_label", "string", physicalType="VARCHAR",
              quality=[_rule("nullValues")])))
    assert _run("generate", "--root", str(tmp_path)) == (0, [])

    seed = _entries(tmp_path / "seeds" / "seeds.yml", "seeds")[1]["band"]
    assert "contract" not in seed
    columns = {column["name"]: column for column in seed["columns"]}
    assert columns["band_order"]["data_tests"] == ["unique"]
    assert columns["band_order"]["tests"] == ["unique", "not_null"]
    assert columns["band_label"] == {"name": "band_label", "data_tests": ["not_null"]}


def test_generate_writes_the_dlt_column_hints(tmp_path):
    """One hints module for every dlt-loaded table, typed from the contract's `physicalType`."""
    _repo(tmp_path, sources={"tlc": ("bronze", ["tripdata"])})
    _contract(tmp_path, "bronze", "tripdata", schema=_element(
        "tripdata",
        _prop("vendor_id", "integer", physicalType="BIGINT", required=True),
        _prop("fare", "number", physicalType="DECIMAL(10,2)"),
        _prop("pickup", "date", physicalType="DATE"),
        _prop("loaded_at", "timestamp", physicalType="TIMESTAMP WITH TIME ZONE")))
    assert _run("generate", "--root", str(tmp_path)) == (0, [])

    module = tmp_path / "ingestion" / "contracts.py"
    namespace: dict = {}
    exec(compile(module.read_text(encoding="utf-8"), str(module), "exec"), namespace)
    assert namespace["COLUMNS"] == {
        "tripdata": {
            "vendor_id": {"data_type": "bigint", "nullable": False},
            "fare": {"data_type": "decimal", "nullable": True},
            "pickup": {"data_type": "date", "nullable": True},
            "loaded_at": {"data_type": "timestamp", "nullable": True},
        }
    }


def test_generate_twice_changes_nothing(tmp_path):
    """A re-run reproduces every generated file byte for byte."""
    _repo(tmp_path, models=["a_model"], sources={"tlc": ("bronze", ["tripdata"])},
          files={"models/core/_core.yml": CORE_PROPERTIES})
    _contract(tmp_path, "core", "a_model", schema=_element(
        "a_model", _prop("trip_key", "string", physicalType="VARCHAR")))
    _contract(tmp_path, "bronze", "tripdata", schema=_element(
        "tripdata", _prop("vendor_id", "integer", physicalType="BIGINT")))
    assert _run("generate", "--root", str(tmp_path)) == (0, [])

    written = [tmp_path / "models" / "core" / "_core.yml",
               tmp_path / "ingestion" / "contracts.py"]
    first = [path.read_text(encoding="utf-8") for path in written]
    assert _run("generate", "--root", str(tmp_path)) == (0, [])
    assert [path.read_text(encoding="utf-8") for path in written] == first
    assert _run("check", "--root", str(tmp_path)) == (0, [])


def test_check_reports_a_generated_key_removed_by_hand(tmp_path):
    """One computation: `check` diffs exactly what `generate` would write."""
    _repo(tmp_path, models=["a_model"],
          files={"models/core/_core.yml": CORE_PROPERTIES})
    _contract(tmp_path, "core", "a_model", schema=_element(
        "a_model",
        _prop("trip_key", "string", physicalType="VARCHAR"),
        _prop("total_amount", "number", physicalType="DECIMAL(10,2)")))
    assert _run("generate", "--root", str(tmp_path)) == (0, [])
    assert _run("check", "--root", str(tmp_path)) == (0, [])

    path = tmp_path / "models" / "core" / "_core.yml"
    doc, _ = _entries(path)
    model = doc["models"][0]
    del model["contract"]
    del model["columns"][1]["data_type"]
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")

    code, diags = _run("check", "--root", str(tmp_path))
    assert (code, _codes(diags)) == (1, ["generated/stale", "generated/stale"])
    assert all("_core.yml" in diag["message"] for diag in diags)
    assert any("a_model.contract" in diag["message"] for diag in diags)
    assert any("a_model.columns.total_amount.data_type" in diag["message"] for diag in diags)

    assert _run("generate", "--root", str(tmp_path)) == (0, [])
    assert _run("check", "--root", str(tmp_path)) == (0, [])


def test_generate_says_so_when_the_map_declares_no_contract_path(tmp_path):
    """A repo that has not adopted contracts gets a diagnosis, not a traceback."""
    (tmp_path / "repo-map.json").write_text(json.dumps({"artifact_paths": {}, "layers": {}}))
    code, diags = _run("generate", "--root", str(tmp_path))
    assert (code, _codes(diags)) == (1, ["contract/unconfigured"])


def test_generate_refuses_a_contract_whose_servers_disagree_with_the_map(tmp_path):
    """Write nothing from a contract that is already inconsistent with the map."""
    _repo(tmp_path, models=["a_model"],
          files={"models/core/_core.yml": CORE_PROPERTIES})
    servers = [{"type": "duckdb", "database": "domain.duckdb", "schema": "staging"}]
    _contract(tmp_path, "core", "a_model", servers=servers, schema=_element(
        "a_model", _prop("trip_key", "string", physicalType="VARCHAR")))

    code, diags = _run("generate", "--root", str(tmp_path))
    assert (code, _codes(diags)) == (1, ["contract/servers-schema"])
    assert "'staging'" in diags[0]["message"] and "'core'" in diags[0]["message"]
    assert (tmp_path / "models" / "core" / "_core.yml").read_text() == CORE_PROPERTIES

    _contract(tmp_path, "core", "a_model", servers=[{**servers[0], "schema": "core"}],
              schema=_element(
                  "a_model", _prop("trip_key", "string", physicalType="VARCHAR")))
    assert _run("generate", "--root", str(tmp_path)) == (0, [])


def test_check_reports_a_generated_module_that_no_longer_parses(tmp_path):
    """A hand-mangled module is stale, not a traceback: stdout stays JSON."""
    _repo(tmp_path, sources={"tlc": ("bronze", ["tripdata"])})
    _contract(tmp_path, "bronze", "tripdata", schema=_element(
        "tripdata", _prop("vendor_id", "integer", physicalType="BIGINT")))
    _generated(tmp_path)

    module = tmp_path / "ingestion" / "contracts.py"
    module.write_text(module.read_text(encoding="utf-8") + "(\n", encoding="utf-8")

    code, diags = _run("check", "--root", str(tmp_path))
    assert (code, _codes(diags)) == (1, ["generated/stale"])
    assert "ingestion/contracts.py" in diags[0]["message"]
    assert "COLUMNS" in diags[0]["message"]


def test_check_reports_a_missing_generated_module(tmp_path):
    """Contract present and `generate` never run is the staleness the gate exists for."""
    _repo(tmp_path, sources={"tlc": ("bronze", ["tripdata"])})
    _contract(tmp_path, "bronze", "tripdata", schema=_element(
        "tripdata", _prop("vendor_id", "integer", physicalType="BIGINT")))

    code, diags = _run("check", "--root", str(tmp_path))
    assert (code, _codes(diags)) == (1, ["generated/stale"])
    assert "ingestion/contracts.py" in diags[0]["message"]


def test_check_reports_a_model_with_no_generated_entry(tmp_path):
    """A contract whose properties entry was never generated is stale, not silent."""
    _repo(tmp_path, models=["a_model"])
    _contract(tmp_path, "core", "a_model", schema=_element(
        "a_model", _prop("trip_key", "string", physicalType="VARCHAR")))

    code, diags = _run("check", "--root", str(tmp_path))
    assert (code, _codes(diags)) == (1, ["generated/stale"])
    assert "models/core/_generated.yml" in diags[0]["message"]
    assert "models.a_model" in diags[0]["message"]


def test_check_reports_a_contract_hand_written_on_a_seed(tmp_path):
    """Seeds never carry a contract; one added by hand is a generated key out of place."""
    _repo(tmp_path, seeds=["band"], files={"seeds/seeds.yml": """version: 2

seeds:
  - name: band
    contract: {enforced: true}
    columns:
      - name: band_order
        data_tests: [unique]
"""})
    _contract(tmp_path, "seeds", "band", schema=_element(
        "band", _prop("band_order", "integer", quality=[_rule("duplicateValues")])))

    code, diags = _run("check", "--root", str(tmp_path))
    assert (code, _codes(diags)) == (1, ["generated/stale"])
    assert "band.contract" in diags[0]["message"]


def test_check_reports_a_data_type_on_a_column_the_contract_never_declares(tmp_path):
    """`check` proves the owned keys are absent where the contract does not own them, too."""
    _repo(tmp_path, models=["a_model"],
          files={"models/core/_core.yml": CORE_PROPERTIES})
    _contract(tmp_path, "core", "a_model", schema=_element(
        "a_model", _prop("trip_key", "string", physicalType="VARCHAR")))
    _generated(tmp_path)
    assert _run("check", "--root", str(tmp_path)) == (0, [])

    path = tmp_path / "models" / "core" / "_core.yml"
    doc, _ = _entries(path)
    doc["models"][0]["columns"][1]["data_type"] = "VARCHAR"
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")

    code, diags = _run("check", "--root", str(tmp_path))
    assert (code, _codes(diags)) == (1, ["generated/stale"])
    assert "a_model.columns.total_amount.data_type" in diags[0]["message"]


def test_hand_written_data_tests_on_a_model_column_are_not_stale(tmp_path):
    """`data_tests` is dbt's own spelling; `generate` never writes it on a model, so it is not ours."""
    _repo(tmp_path, models=["a_model"],
          files={"models/core/_core.yml": MODEL_WITH_DATA_TESTS})
    _contract(tmp_path, "core", "a_model", schema=_element(
        "a_model", _prop("trip_key", "string", physicalType="VARCHAR")))
    _generated(tmp_path)

    assert _run("check", "--root", str(tmp_path)) == (0, [])
    column = _entries(tmp_path / "models" / "core" / "_core.yml")[1]["a_model"]["columns"][0]
    assert column["data_tests"] == ["unique", "not_null"]
    assert column["data_type"] == "VARCHAR"


def test_hand_written_data_type_on_a_seed_column_is_not_stale(tmp_path):
    """A seed carries generated `data_tests`; a `data_type` there is hand-written and not ours."""
    _repo(tmp_path, seeds=["band"], files={"seeds/seeds.yml": SEED_WITH_DATA_TYPE})
    _contract(tmp_path, "seeds", "band", schema=_element(
        "band", _prop("band_order", "integer", quality=[_rule("duplicateValues")])))
    _generated(tmp_path)

    assert _run("check", "--root", str(tmp_path)) == (0, [])
    column = _entries(tmp_path / "seeds" / "seeds.yml", "seeds")[1]["band"]["columns"][0]
    assert column == {"name": "band_order", "data_type": "INTEGER", "data_tests": ["unique"]}


def test_generate_augments_a_zero_indent_properties_file(tmp_path):
    """A block sequence at its key's indent is one entry; a second is dbt's hard parse error."""
    _repo(tmp_path, models=["a_model"],
          files={"models/core/_core.yml": ZERO_INDENT_PROPERTIES})
    _contract(tmp_path, "core", "a_model", schema=_element(
        "a_model", _prop("trip_key", "string", physicalType="VARCHAR")))
    _generated(tmp_path)

    assert _run("check", "--root", str(tmp_path)) == (0, [])
    text = (tmp_path / "models" / "core" / "_core.yml").read_text(encoding="utf-8")
    assert text.count("- name: a_model") == 1
    model = yaml.safe_load(text)["models"][0]
    assert model["contract"] == {"enforced": True}
    assert model["columns"] == [
        {"name": "trip_key", "description": "kept", "data_type": "VARCHAR"}
    ]



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


def _repo(tmp_path, models=(), seeds=(), sources=None):
    """A minimal repo the tool can resolve: layers, seeds and a source's resource docs."""
    (tmp_path / "repo-map.json").write_text(
        json.dumps(
            {
                "artifact_paths": {"data_contract": "contracts/{schema}/{table}.odcs.yaml"},
                "layers": {
                    "core": {"schema": "core", "path": "models/core/", "built_by": "dbt"},
                    "seeds": {"schema": "seeds", "path": "seeds/", "built_by": "dbt"},
                },
                "sources": sources or {},
            }
        )
    )
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
        (tmp_path / "repo-map.json").write_text(
            json.dumps(
                {
                    **json.loads((tmp_path / "repo-map.json").read_text()),
                    "sources": {
                        name: {"kind": "dlt", "dataset": dataset, "docs": f"ingestion/docs/{name}.yml"}
                    },
                }
            )
        )
    return tmp_path


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

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

MINIMAL = {
    "apiVersion": "v3.2.0",
    "kind": "DataContract",
    "id": "c0ffee00-0000-4000-8000-000000000001",
    "name": "a_relation",
    "version": "1.0.0",
}


def _run(*args):
    """Invoke the CLI; stdout is always pure JSON."""
    result = RUNNER.invoke(app, list(args))
    assert result.exit_code in (0, 1, 2), result.output
    return result.exit_code, json.loads(result.stdout or "[]")


def _write(tmp_path, name, doc):
    target = tmp_path / name
    target.write_text(yaml.safe_dump(doc))
    return target


def test_check_accepts_a_minimal_contract(tmp_path):
    """The vendored schema resolves and a document carrying the four required keys validates."""
    _write(tmp_path, "a_relation.odcs.yaml", MINIMAL)
    code, diags = _run("check", str(tmp_path))
    assert (code, diags) == (0, [])


def test_check_rejects_a_key_the_standard_does_not_define(tmp_path):
    """`additionalProperties` is closed, so an invented section is an error, not a warning."""
    _write(tmp_path, "a_relation.odcs.yaml", {**MINIMAL, "pricing": {}})
    code, diags = _run("check", str(tmp_path))
    assert code == 1
    assert [d["code"] for d in diags] == ["schema/invalid"]
    assert "pricing" in diags[0]["message"]

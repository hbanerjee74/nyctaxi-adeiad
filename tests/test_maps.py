import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[1]
REPO_MAP = json.loads((ROOT / "repo-map.json").read_text())
TEST_MAP = json.loads((ROOT / "test-map.json").read_text())


def _exists(path: str) -> bool:
    """A path with a {placeholder} is checked up to the last whole directory before it."""
    prefix = re.split(r"[{*]", path)[0]
    static = prefix.rstrip("/") if prefix.endswith("/") or "/" not in prefix else prefix.rsplit("/", 1)[0]
    return (ROOT / static).exists() if static else True


def test_repo_map_validates_against_its_schema():
    schema = json.loads((ROOT / "repo-map.schema.json").read_text())
    jsonschema.validate(REPO_MAP, schema)


def test_repo_map_names_every_layer_with_one_builder():
    assert set(REPO_MAP["layers"]) == {
        "bronze", "staging", "intermediate", "core", "agg", "finance", "ops", "ops_raw", "mdm_raw",
    }
    assert {layer["built_by"] for layer in REPO_MAP["layers"].values()} == {"dlt", "dbt"}


def test_repo_map_paths_exist():
    paths = [layer["path"] for layer in REPO_MAP["layers"].values()]
    paths += REPO_MAP["artifact_paths"].values()
    paths += REPO_MAP["entrypoints"].values()
    paths += REPO_MAP["key_directories"].keys()
    paths += [m["path"] for m in REPO_MAP["modules"].values()]
    for source in REPO_MAP["sources"].values():
        paths += [source[k] for k in ("pipeline", "docs", "module", "tests", "design_record")]
    missing = [p for p in paths if not _exists(p)]
    assert missing == []


def test_every_source_is_registered_in_the_dlt_config():
    config = tomllib.loads((ROOT / "ingestion" / ".dlt" / "config.toml").read_text())
    for name, source in REPO_MAP["sources"].items():
        assert source["config_section"] == f"sources.{name}"
        assert name in config["sources"], f"{name} has no [sources.{name}] section"


def test_every_layer_has_a_test_map_module():
    modules = set(TEST_MAP["modules"])
    for name, layer in REPO_MAP["layers"].items():
        expected = "ingestion" if layer["built_by"] == "dlt" else name
        assert expected in modules, f"layer {name} has no test-map module {expected}"


def test_source_artifact_patterns_resolve_for_every_source():
    for name in REPO_MAP["sources"]:
        for key in ("source_module", "source_tests", "pipeline", "resource_docs", "design_record_pipeline"):
            pattern = REPO_MAP["artifact_paths"][key]
            path = pattern.format(name=name, connection=name, pipeline=name)
            assert (ROOT / path).exists(), f"{key} for {name}: {path}"


def test_every_dlt_layer_has_a_source():
    datasets = {s["dataset"] for s in REPO_MAP["sources"].values()}
    dlt_schemas = {l["schema"] for l in REPO_MAP["layers"].values() if l["built_by"] == "dlt"}
    assert datasets == dlt_schemas


def test_test_map_paths_exist():
    missing = []
    for name, module in TEST_MAP["modules"].items():
        for key in ("sources", "unit", "data"):
            missing += [f"{name}.{key}: {p}" for p in module.get(key, []) if not _exists(p)]
    assert missing == []


def _dbt_ls(select: str, resource_type: str, exclude: str | None = None) -> list[str]:
    command = [sys.executable, "-m", "dbt.cli.main", "ls", "--select", select, "--resource-type", resource_type]
    if exclude:
        command += ["--exclude", exclude]
    out = subprocess.run(command, cwd=ROOT / "transformation", capture_output=True, text=True, check=True).stdout
    return [line for line in out.splitlines() if ":" in line and not line.startswith(" ")]


DBT_SELECTORS = [
    (name, kind, module["selectors"][kind])
    for name, module in TEST_MAP["modules"].items()
    for kind in ("data", "unit")
    if kind in module.get("selectors", {})
]


@pytest.mark.parametrize("name,kind,select", DBT_SELECTORS, ids=lambda v: str(v))
def test_test_map_dbt_selectors_resolve_to_at_least_one_test(name, kind, select):
    if kind == "unit":
        nodes = _dbt_ls(select, "unit_test")
    else:
        nodes = _dbt_ls(select, "test", exclude="test_type:unit")
    assert nodes, f"{name}.{kind}: `{select}` selects no tests"

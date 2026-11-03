"""Dry run of the onboarding skill's greenfield path: bootstrap a Domain from the templates, then gate it.

`.agents/skills/onboarding/references/greenfield.md` says what to write from `templates/`. This test
writes it into a scratch directory with sample answers, seeds the four skills that always ship
(`data-contract`, `validating-data-contract`, `ontology`, `validating-ontology`) from this repo's
copies, and runs the plugin's own gates against the result: the template's map tests, the ontology
validator, the contract check, and `generate` for a first input contract that precedes its table
(`status: proposed`). A template that drifts from the semantic ownership model fails here.

`dbt parse` is left out (it installs a package from the hub); the Domain's own `test_maps.py` runs it.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
ONBOARDING = ROOT / ".agents" / "skills" / "onboarding"
TEMPLATES = ONBOARDING / "templates"
SKILLS = ROOT / ".agents" / "skills"
SEEDED = ("data-contract", "validating-data-contract", "ontology", "validating-ontology")
CONVENTIONS = ("adr", "context", "dbt-models", "dbt-testing", "design-records", "dlt", "git-and-prs", "sql-style", "workarounds")
PROJECT = "scratch_domain"
RAW_SCHEMA = "raw_orders"

for _module in ("duckdb", "jsonschema", "sqlglot", "typer", "yaml"):
    pytest.importorskip(_module)


def _copy(src: Path, dest: Path, **placeholders: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    text = src.read_text()
    for key, value in placeholders.items():
        text = text.replace(key, value)
    dest.write_text(text)


def _keep(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / ".gitkeep").write_text("")


def bootstrap(dest: Path) -> None:
    """The Build step of greenfield.md, with a raw schema, one mart area and the DuckDB-local platform."""
    name = {"<project_name>": PROJECT}
    for template in ("dbt_project.yml", "packages.yml", "profiles.yml"):
        _copy(TEMPLATES / "dbt" / template, dest / "transformation" / template, **name)
    for macro in ("relations.sql", "generate_schema_name.sql"):
        _copy(TEMPLATES / "dbt" / macro, dest / "transformation" / "macros" / macro)
    for folder in ("models/staging", "models/intermediate", "models/marts/core", "tests", "seeds"):
        _keep(dest / "transformation" / folder)
    (dest / "transformation" / "models" / "staging" / "_sources.yml").write_text("version: 2\n")
    _copy(TEMPLATES / "dlt" / "config.toml", dest / "ingestion" / ".dlt" / "config.toml")
    _copy(TEMPLATES / "dlt" / "requirements.txt", dest / "ingestion" / "requirements.txt")
    _keep(dest / "ingestion" / "sources")
    for script in ("run_all.py", "run_ingest.py", "run_transform.py"):
        _copy(TEMPLATES / "orchestration" / script, dest / "orchestration" / script, **name)
    _copy(TEMPLATES / "tests" / "conftest.py", dest / "tests" / "conftest.py")
    _copy(TEMPLATES / "tests" / "test_run.py", dest / "tests" / "orchestration" / "test_run.py")
    for test in ("test_maps.py", "test_adr_links.py"):
        _copy(TEMPLATES / "tests" / test, dest / "tests" / test)

    repo_map = (TEMPLATES / "repo" / "repo-map.json").read_text()
    for key, value in {
        "<UTC timestamp>": "2026-11-03T00:00:00Z",
        "<domain slug>": "scratch",
        "<one line>": "A scratch Domain for the onboarding dry run.",
        "<raw schema>": RAW_SCHEMA,
        "<source system>": "Order system",
        "<data platform>": "duckdb_local",
    }.items():
        repo_map = repo_map.replace(key, value)
    (dest / "repo-map.json").write_text(repo_map)
    test_map = (TEMPLATES / "repo" / "test-map.json").read_text().replace("<UTC timestamp>", "2026-11-03T00:00:00Z")
    (dest / "test-map.json").write_text(test_map)
    shutil.copy(TEMPLATES / "repo" / "repo-map.schema.json", dest / "repo-map.schema.json")
    for template, target in (("requirements-dev.txt", "requirements-dev.txt"), ("ruff.toml", "ruff.toml"), ("AGENTS.md", "AGENTS.md")):
        _copy(TEMPLATES / "repo" / template, dest / target)

    for folder in ("docs/adr", "docs/design", "docs/review", "docs/proposal", "contracts", "ontology"):
        _keep(dest / folder)
    (dest / "CONTEXT.md").write_text("# Scratch\n")
    for skill in SEEDED:
        shutil.copytree(SKILLS / skill, dest / ".agents" / "skills" / skill, ignore=shutil.ignore_patterns("__pycache__"))
    # No boundary mart yet, so no semantic-model skill: only the checker the ontology validates through.
    shutil.copytree(
        SKILLS / "semantic-model" / "scripts",
        dest / ".agents" / "skills" / "semantic-model" / "scripts",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    for skill in CONVENTIONS:
        _copy(TEMPLATES / "skills" / f"{skill}.md", dest / ".agents" / "skills" / skill / "SKILL.md")


def _run(command: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)


def _diagnostics(result: subprocess.CompletedProcess) -> list[dict]:
    return json.loads(result.stdout)


@pytest.fixture(scope="module")
def domain(tmp_path_factory) -> Path:
    dest = tmp_path_factory.mktemp("greenfield")
    bootstrap(dest)
    return dest


def test_the_template_maps_declare_roles_the_boundary_and_the_platform(domain):
    repo_map = json.loads((domain / "repo-map.json").read_text())
    assert {name: layer["role"] for name, layer in repo_map["layers"].items()} == {
        RAW_SCHEMA: "input",
        "staging": "internal",
        "intermediate": "internal",
        "core": "boundary",
    }
    assert "gold_layers" not in repo_map
    assert repo_map["semantic_exclusions"] == []
    assert repo_map["data_platform"] == "duckdb_local"
    assert repo_map["artifact_paths"]["data_contract"] == "contracts/{schema}/{table}.odcs.yaml"
    assert {"contracts", "ontology"} <= set(json.loads((domain / "test-map.json").read_text())["modules"])


def test_nothing_the_templates_seed_names_a_medallion_layer_or_a_retired_construct():
    """What a new Domain receives is by role; the references may name a retired term to file it as a finding."""
    retired = ("medallion", "gold", "silver", "bronze", "metricflow", "_semantic.yml", "standalone")
    offenders = []
    for path in sorted(TEMPLATES.rglob("*")):
        if path.is_file():
            # The plugin's script `run_bronze_tier1_tests.py` and the map test's guard against the
            # retired `gold_layers` key are the two places a retired word is a proper name.
            text = path.read_text().lower().replace("run_bronze_tier1_tests", "").replace("gold_layers", "")
            offenders += [f"{path.relative_to(TEMPLATES)}: {word}" for word in retired if word in text]
    assert offenders == []


def test_the_bootstrapped_domain_passes_its_own_map_tests(domain):
    result = _run([sys.executable, "-m", "pytest", "tests", "-q", "-p", "no:cacheprovider", "-k", "not parses and not selectors"], domain)
    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-1000:]


def test_the_ontology_and_contract_gates_pass_on_the_bootstrapped_domain(domain):
    assert not (domain / ".agents" / "skills" / "semantic-model" / "SKILL.md").exists()
    ossie = domain / ".agents" / "skills" / "semantic-model" / "scripts" / "ossie.py"
    odcs = domain / ".agents" / "skills" / "data-contract" / "scripts" / "odcs.py"
    # An empty ontology/ has nothing to validate; the first concept is what registers the command.
    empty = _run([sys.executable, str(ossie), "validate", "ontology/"], domain)
    assert [d["code"] for d in _diagnostics(empty)] == ["cli/no-files"]
    (domain / "ontology" / "scratch.ontology.yaml").write_text(
        yaml.safe_dump(
            {
                "version": "0.2.0.dev0",
                "name": "scratch",
                "description": "The business vocabulary of the scratch Domain.",
                "ontology": [
                    {"concept": "OrderId", "description": "The source system's identifier for one order.", "type": "ValueType", "extends": ["Integer"]}
                ],
            },
            sort_keys=False,
        )
    )
    ontology = _run([sys.executable, str(ossie), "validate", "ontology/"], domain)
    assert ontology.returncode == 0, ontology.stdout + ontology.stderr
    glossary = _run([sys.executable, str(ossie), "glossary", "ontology/", "CONTEXT.md"], domain)
    assert glossary.returncode == 0, glossary.stdout + glossary.stderr
    contracts = _run([sys.executable, str(odcs), "check"], domain)
    assert contracts.returncode == 0, contracts.stdout
    assert [d for d in _diagnostics(contracts) if d["severity"] != "info"] == []


def test_a_proposed_input_contract_generates_the_dlt_hints_before_its_table_exists(domain):
    contract = {
        "apiVersion": "v3.2.0",
        "kind": "DataContract",
        "id": "00000000-0000-5000-8000-000000000001",
        "name": "orders",
        "version": "1.0.0",
        "status": "proposed",
        "servers": [{"server": "scratch", "type": "duckdb", "database": "domain.duckdb", "schema": RAW_SCHEMA}],
        "schema": [
            {
                "name": "orders",
                "properties": [
                    {
                        "name": "order_id",
                        "description": "Identifier of the order at the source system.",
                        "logicalType": "integer",
                        "physicalType": "BIGINT",
                        "primaryKey": True,
                    },
                    {
                        "name": "placed_at",
                        "description": "When the order was placed.",
                        "logicalType": "timestamp",
                        "physicalType": "TIMESTAMP",
                    },
                ],
            }
        ],
    }
    path = domain / "contracts" / RAW_SCHEMA / "orders.odcs.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(contract, sort_keys=False))
    odcs = domain / ".agents" / "skills" / "data-contract" / "scripts" / "odcs.py"
    generated = _run([sys.executable, str(odcs), "generate"], domain)
    assert generated.returncode == 0, generated.stdout + generated.stderr
    hints = (domain / "ingestion" / "contracts.py").read_text()
    assert '"orders"' in hints and '"order_id"' in hints
    checked = _run([sys.executable, str(odcs), "check"], domain)
    assert checked.returncode == 0, checked.stdout
    # The key states the grain: no `contract/no-grain`, and nothing else beyond information.
    assert [d for d in _diagnostics(checked) if d["severity"] != "info"] == []

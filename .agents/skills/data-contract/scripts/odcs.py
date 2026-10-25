"""ODCS data-contract tooling for this repo.

Commands: `check` (schema and structure of the committed contracts), `check --relations`
(adds the comparison against the built relation), `reverse` (draft contracts from an
existing warehouse), `generate` (write the dbt keys and dlt hints from the contracts).

This script proves shape and reports facts. It never judges meaning: the grain, whether a
`required` is honest, and whether a quality rule encodes the real business answer are the
`validating-data-contract` review, not a pass/fail here.

Every location resolves from `repo-map.json`: a layer's `path` for the dbt models it builds,
the seeds layer for its CSVs, and a source's `docs` file for the resources it lands. The
warehouse is consulted only by `--relations`.

Usage:
  python3 scripts/odcs.py check [--root PATH] [--relations]

JSON diagnostics go to stdout (agent-parseable); human prose to stderr.
Exit 0 when no errors (warnings allowed), 1 otherwise.
"""

import json
import re
from pathlib import Path

import jsonschema
import typer
import yaml

APP_DIR = Path(__file__).resolve().parent
VENDOR_DIR = APP_DIR / "odcs_vendor"
SCHEMA_FILE = VENDOR_DIR / "odcs-json-schema-v3.2.0.json"
SPEC_VERSION = "v3.2.0"
UPSTREAM_COMMIT = "8b551607aad6801979bf4c209385e78fc4d029e5"

# Sections that assert something. A present-but-empty one claims a promise nobody made.
ROOT_SECTIONS = ("servers", "authoritativeDefinitions", "tags")

app = typer.Typer(add_completion=False)


def _diag(severity: str, code: str, message: str) -> dict:
    return {"severity": severity, "code": code, "message": message}


def _repo_root(start: Path) -> Path:
    """The repo root, found by the map rather than by depth, so a seeded skill still resolves."""
    for candidate in [start, *start.parents]:
        if (candidate / "repo-map.json").is_file():
            return candidate
    raise typer.BadParameter(f"no repo-map.json above {start}")


def _repo_map(root: Path) -> dict:
    return json.loads((root / "repo-map.json").read_text(encoding="utf-8"))


def _declared(root: Path, raw: str) -> Path:
    """The path an artifact pattern names, up to its first placeholder."""
    prefix = raw.split("{")[0].split("*")[0].rstrip("/")
    return root / prefix


def _schema() -> dict:
    """The vendored schema. Never fetched: a validation run is offline by construction."""
    return json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))


def _one_per_defect(diags: list[dict]) -> list[dict]:
    """Collapse the same defect reported twice.

    Draft 2020-12 reports one unknown key as both `additionalProperties` and
    `unevaluatedProperties`. The location and the offending names are the defect; the
    validator that noticed it is not.
    """
    seen = set()
    unique = []
    for diag in diags:
        where = diag["message"].split(": ", 1)[0] + diag["message"].split(": ")[1]
        names = tuple(sorted(set(re.findall(r"'([^']+)'", diag["message"]))))
        key = (diag["code"], where, names)
        if key not in seen:
            seen.add(key)
            unique.append(diag)
    return unique


def _schema_diagnostics(doc: object, path: Path) -> list[dict]:
    """Validate one document against the vendored schema."""
    validator = jsonschema.Draft202012Validator(_schema())
    errors = sorted(validator.iter_errors(doc), key=lambda e: list(e.absolute_path))
    diags = [
        _diag(
            "error",
            "schema/invalid",
            f"{path}: {'.'.join(str(p) for p in error.absolute_path) or '<root>'}: {error.message}",
        )
        for error in errors
    ]
    return _one_per_defect(diags)


def expected_relations(root: Path, repo_map: dict) -> dict[tuple[str, str], str]:
    """Every relation the map declares, as `(schema, table)` mapped to what declares it.

    dbt models and seeds come from the layer paths. Raw relations come from each source's
    resource docs. The loader's audit relations are written by the installed library and
    appear in none of these, so only `--relations` can see them.
    """
    expected: dict[tuple[str, str], str] = {}
    for name, layer in (repo_map.get("layers") or {}).items():
        path = root / layer["path"] if layer.get("path") else None
        if path is None or not path.is_dir():
            continue
        suffix = ".csv" if name == "seeds" else ".sql" if layer.get("built_by") == "dbt" else None
        if suffix is None:
            continue
        for file in sorted(path.rglob(f"*{suffix}")):
            expected[(layer["schema"], file.stem)] = f"layer {name}"
    for name, source in (repo_map.get("sources") or {}).items():
        docs = source.get("docs")
        if not docs:
            continue
        entries = yaml.safe_load((root / docs).read_text(encoding="utf-8")) or {}
        for resource in sorted(entries.get("resources") or {}):
            expected[(source["dataset"], resource)] = f"source {name}"
    return expected


def _contract_relations(root: Path, repo_map: dict) -> dict[tuple[str, str], Path]:
    """Every committed contract, keyed by the relation its path names."""
    base = _declared(root, repo_map["artifact_paths"]["data_contract"])
    found: dict[tuple[str, str], Path] = {}
    if not base.is_dir():
        return found
    for path in sorted(base.rglob("*.odcs.yaml")):
        relative = path.relative_to(base)
        if len(relative.parts) != 2:
            continue
        found[(relative.parts[0], relative.stem.split(".")[0])] = path
    return found


def _empty_sections(doc: dict, path: Path) -> list[dict]:
    diags = []
    for section in ROOT_SECTIONS:
        if section in doc and not doc[section]:
            diags.append(_diag("error", "contract/empty-section",
                               f"{path}: `{section}` is present and empty; omit it instead"))
    for element in doc.get("schema") or []:
        if isinstance(element, dict) and "quality" in element and not element["quality"]:
            diags.append(_diag("error", "contract/empty-section",
                               f"{path}: `schema[].quality` is present and empty; omit it instead"))
    return diags


def _grain(doc: dict, path: Path) -> list[dict]:
    """A warning, not an error: an onboarding run may leave the grain to review."""
    elements = [e for e in (doc.get("schema") or []) if isinstance(e, dict)]
    stated = [e for e in elements if str(e.get("dataGranularityDescription") or "").strip()]
    if stated:
        return []
    return [_diag("warning", "contract/no-grain",
                  f"{path}: no `dataGranularityDescription`; the review refuses a contract "
                  f"a shipped intent presents as complete without one")]


@app.command()
def version():
    """Pin report: tool, standard version and the vendored upstream commit, as JSON."""
    # Also forces Typer group mode so `check` keeps its subcommand name once
    # `reverse` and `generate` land beside it.
    print(json.dumps({"tool": "odcs", "spec": SPEC_VERSION, "upstream_commit": UPSTREAM_COMMIT}))


@app.command()
def check(root: str = "", relations: bool = False):
    """Validate every committed contract against the repo map and the vendored schema.

    `--relations` adds the comparison against the built relation and fails when no catalog
    resolves, rather than skipping: asking for the check and getting silence is the false
    pass it exists to prevent.
    """
    repo_root = Path(root).resolve() if root else _repo_root(APP_DIR)
    repo_map = _repo_map(repo_root)

    if not (repo_map.get("artifact_paths") or {}).get("data_contract"):
        print(json.dumps([_diag(
            "error", "contract/unconfigured",
            "repo-map.json declares no artifact_paths.data_contract, so no contract can be found",
        )]))
        raise typer.Exit(1)

    expected = expected_relations(repo_root, repo_map)
    contracts = _contract_relations(repo_root, repo_map)
    diags: list[dict] = []

    for relation, declarer in sorted(expected.items()):
        if relation not in contracts:
            diags.append(_diag("error", "contract/missing",
                               f"{relation[0]}.{relation[1]}: declared by {declarer} and has no contract"))
    for relation, path in sorted(contracts.items()):
        if relation not in expected:
            diags.append(_diag("error", "contract/orphan",
                               f"{path}: names no relation the map declares"))

    for relation, path in sorted(contracts.items()):
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            diags.append(_diag("error", "schema/invalid", f"{path}: {exc}"))
            continue
        if not isinstance(doc, dict):
            diags.append(_diag("error", "schema/invalid", f"{path}: not a mapping"))
            continue
        diags.extend(_schema_diagnostics(doc, path))
        diags.extend(_empty_sections(doc, path))
        diags.extend(_grain(doc, path))

    if relations:
        diags.append(_diag("error", "relations/not-implemented",
                           "check --relations is not implemented yet"))

    print(json.dumps(diags))
    raise typer.Exit(1 if any(d["severity"] == "error" for d in diags) else 0)


if __name__ == "__main__":
    app()

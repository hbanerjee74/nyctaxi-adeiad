"""ODCS data-contract tooling for this repo.

Commands: `check` (schema and structure of the committed contracts), `check --relations`
(adds the comparison against the built relation), `reverse` (draft contracts from an
existing warehouse), `generate` (write the dbt keys and dlt hints from the contracts).

This script proves shape and reports facts. It never judges meaning: the grain, whether a
`required` is honest, and whether a quality rule encodes the real business answer are the
`validating-data-contract` review, not a pass/fail here.

Every location resolves from `repo-map.json`; nothing is assumed by convention.

Usage:
  python3 scripts/odcs.py check [<dir>]
  python3 scripts/odcs.py check --relations [<dir>]

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

app = typer.Typer(add_completion=False)


def _schema() -> dict:
    """The vendored schema. Never fetched: a validation run is offline by construction."""
    return json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))


def _contract_files(target: Path) -> list[Path]:
    """Every contract under TARGET, in a stable order."""
    if target.is_dir():
        return sorted(target.rglob("*.odcs.yaml"))
    return [target]


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
        {
            "severity": "error",
            "code": "schema/invalid",
            "message": f"{path}: {'.'.join(str(p) for p in error.absolute_path) or '<root>'}: {error.message}",
        }
        for error in errors
    ]
    return _one_per_defect(diags)


@app.command()
def version():
    """Pin report: tool, standard version and the vendored upstream commit, as JSON."""
    # Also forces Typer group mode so `check` keeps its subcommand name once
    # `reverse` and `generate` land beside it.
    print(json.dumps({"tool": "odcs", "spec": SPEC_VERSION, "upstream_commit": UPSTREAM_COMMIT}))


@app.command()
def check(target: str = typer.Argument("."), relations: bool = False):
    """Validate every contract under TARGET.

    `--relations` adds the comparison against the built relation and fails when no catalog
    resolves, rather than skipping: asking for the check and getting silence is the false
    pass it exists to prevent.
    """
    if relations:
        raise typer.Exit(_relations_not_implemented())

    files = _contract_files(Path(target))
    diags: list[dict] = []
    for path in files:
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            diags.append(
                {"severity": "error", "code": "schema/invalid", "message": f"{path}: {exc}"}
            )
            continue
        diags.extend(_schema_diagnostics(doc, path))

    print(json.dumps(diags))
    raise typer.Exit(1 if any(d["severity"] == "error" for d in diags) else 0)


def _relations_not_implemented() -> int:
    """The catalog comparison lands with the relation checks; say so instead of passing."""
    print(
        json.dumps(
            [
                {
                    "severity": "error",
                    "code": "relations/not-implemented",
                    "message": "check --relations is not implemented yet",
                }
            ]
        )
    )
    return 1


if __name__ == "__main__":
    app()

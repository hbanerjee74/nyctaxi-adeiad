"""Ossie canonical-model tooling for this repo.

Today: `validate` only. `export` (dbt/Tableau/PowerBI) is an explicit
follow-up (VD-7126); nothing here writes consumer files.

Usage:
  python3 tools/ossie.py validate logical-model/nyc_taxi_analytics.ossie.yaml
  python3 tools/ossie.py validate logical-model/

JSON diagnostics go to stdout (agent-parseable); human prose to stderr.
Exit 0 when no errors (warnings allowed), 1 otherwise.
"""

import importlib.util
import json
import sys
from pathlib import Path

import typer

sys.path.insert(0, str(Path(__file__).parent))

from ossie_vibedata import validate_vibedata  # noqa: E402

TOOLS_DIR = Path(__file__).parent
VENDOR_DIR = TOOLS_DIR / "ossie_vendor"

_spec = importlib.util.spec_from_file_location(
    "ossie_vendor_validate", VENDOR_DIR / "validate.py")
_vendor = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_vendor)

app = typer.Typer(no_args_is_help=True)


def _resolve_targets(model: str) -> list[Path]:
    p = Path(model)
    if p.is_dir():
        return sorted(p.glob("*.ossie.yaml"))
    return [p]


def _as_diag(entry) -> dict:
    if isinstance(entry, _vendor.ValidationWarning):
        return {"severity": "warning", "message": str(entry)}
    if isinstance(entry, dict):
        return entry
    return {"severity": "error", "message": str(entry)}


UPSTREAM_PIN = "c5cb931d72029dc523a5dd18d267f083403786f2"
UPSTREAM_DATE = "2026-10-14"
SPEC_VERSION = "0.2.0.dev0"
TOOL_VERSION = "0.1.0"


@app.command()
def version():
    """Pin report: tool, spec, and upstream validator commit, as JSON."""
    # Also forces Typer group mode so `validate` keeps its subcommand name
    # when `export` lands as a second command.
    print(json.dumps({"tool": TOOL_VERSION, "spec": SPEC_VERSION,
                      "upstream_commit": UPSTREAM_PIN, "upstream_date": UPSTREAM_DATE}))


def _read_text(target: Path):
    """Read UTF-8 text, returning (text, diag); never prints (stdout is JSON)."""
    try:
        return target.read_text(encoding="utf-8"), None
    except OSError as e:
        return None, {"severity": "error", "code": "cli/unreadable",
                      "message": f"Could not read '{target}': {e}"}
    except UnicodeDecodeError as e:
        return None, {"severity": "error", "code": "cli/unreadable",
                      "message": f"'{target}' is not valid UTF-8 text: {e}"}


def _load_schema():
    """Load and metaschema-check the vendored schema; (schema, diag)."""
    path = VENDOR_DIR / "ossie-schema.json"
    text, diag = _read_text(path)
    if diag:
        return None, diag
    try:
        schema = json.loads(text)
    except json.JSONDecodeError as e:
        return None, {"severity": "error", "code": "cli/bad-schema",
                      "message": f"Invalid JSON in schema {path}: {e}"}
    try:
        _vendor.Draft202012Validator.check_schema(schema)
    except _vendor.SchemaError as e:
        return None, {"severity": "error", "code": "cli/bad-schema",
                      "message": f"Invalid schema {path}: {e.message}"}
    return schema, None


@app.command()
def validate(model: str):
    """Validate canonical file(s): upstream core checks + VIBEDATA pass."""
    targets = _resolve_targets(model)
    if not targets:
        print(json.dumps([{"severity": "error", "code": "cli/no-files",
                           "message": f"No *.ossie.yaml under '{model}'"}]))
        raise typer.Exit(1)
    schema, schema_diag = _load_schema()
    if schema_diag:
        print(json.dumps([schema_diag]))
        raise typer.Exit(2)
    diags = []
    for target in targets:
        text, read_diag = _read_text(target)
        if read_diag:
            read_diag["file"] = str(target)
            diags.append(read_diag)
            continue
        try:
            data = _vendor.load_yaml_named(text, str(target))
        except Exception as e:  # noqa: BLE001 - report, don't crash
            diags.append({"severity": "error", "code": "cli/bad-yaml", "file": str(target),
                          "message": f"'{target}': invalid YAML: {e}"})
            continue
        try:
            file_diags = [_as_diag(e) for e in _vendor.validate_document(data, schema)]
            if not any(d["severity"] == "error" for d in file_diags):
                file_diags.extend(validate_vibedata(data))
        except Exception as e:  # noqa: BLE001 - a check bug must not kill JSON output
            file_diags = [{"severity": "error", "code": "cli/check-crashed",
                           "message": f"'{target}': validator crashed: {type(e).__name__}: {e}"}]
        for d in file_diags:
            d.setdefault("file", str(target))
        diags.extend(file_diags)
    print(json.dumps(diags, indent=2))
    errors = [d for d in diags if d["severity"] == "error"]
    typer.echo(f"{len(targets)} file(s), {len(errors)} error(s).", err=True)
    raise typer.Exit(1 if errors else 0)


if __name__ == "__main__":
    app()

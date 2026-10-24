"""Ossie canonical-model tooling for this repo.

Commands: `validate` (core + VIBEDATA + ontology), `coverage` (models on disk
vs `dbt_model` names), `refs` (mapping references), `glossary` (ontology vs
`CONTEXT.md`), `version`. `export` (dbt/Tableau/PowerBI) is an explicit
follow-up (VD-7126); nothing here writes consumer files.

Usage:
  python3 scripts/ossie.py validate <file-or-dir>
  python3 scripts/ossie.py coverage <model-file-or-dir> <model-root>
  python3 scripts/ossie.py suppliers <model-file-or-dir>
  python3 scripts/ossie.py notes <model-file-or-dir> <tests-dir> [adr-dir]
  python3 scripts/ossie.py level-tests <model-dir> <test-file> [--check]
  python3 scripts/ossie.py content-tests <model-dir> <test-file> [--check]
  python3 scripts/ossie.py compile <model-file> <query-file>
  python3 scripts/ossie.py columns <model-file-or-dir> <dbt-catalog.json>
  python3 scripts/ossie.py refs <ontology-dir> <model-dir>
  python3 scripts/ossie.py glossary <ontology-dir> <context-md>
  python3 scripts/ossie.py version

JSON diagnostics go to stdout (agent-parseable); human prose to stderr.
Exit 0 when no errors (warnings allowed), 1 otherwise.
"""

import importlib.util
import json
import re
import sys
from pathlib import Path

import typer

sys.path.insert(0, str(Path(__file__).parent))

from ossie_columns import check as check_columns  # noqa: E402
from ossie_columns import relations as catalog_relations  # noqa: E402
from ossie_compile import CompileError, Model, Query, compile_query  # noqa: E402
from ossie_content import generate as generate_content_tests  # noqa: E402
from ossie_levels import generate as generate_level_tests  # noqa: E402
from ossie_vibedata import (  # noqa: E402
    _names_in,
    metric_dimensionality,
    physical_table_index,
    validate_vibedata,
)

TOOLS_DIR = Path(__file__).parent
VENDOR_DIR = TOOLS_DIR / "ossie_vendor"

_spec = importlib.util.spec_from_file_location(
    "ossie_vendor_validate", VENDOR_DIR / "validation" / "validate.py")
_vendor = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_vendor)

app = typer.Typer(no_args_is_help=True)


MODEL_SUFFIX = ".ossie.yaml"
ONTOLOGY_SUFFIX = ".ontology.yaml"
MAPPING_SUFFIX = ".mapping.yaml"
SUFFIXES = (MODEL_SUFFIX, ONTOLOGY_SUFFIX, MAPPING_SUFFIX)


def _resolve_targets(model: str) -> list[Path]:
    """Model documents only: the commands that read datasets and metrics."""
    p = Path(model)
    if p.is_dir():
        return sorted(p.glob(f"*{MODEL_SUFFIX}"))
    return [p]


def _canonical_targets(path: str) -> list[Path]:
    """Every canonical document under a path: models, ontologies and mappings."""
    p = Path(path)
    if p.is_dir():
        return sorted(item for suffix in SUFFIXES for item in p.glob(f"*{suffix}"))
    return [p]


def _kind(doc) -> str:
    """A canonical document's kind, from the key that only it carries."""
    if isinstance(doc, dict) and "concept_mappings" in doc:
        return "mapping"
    if isinstance(doc, dict) and "ontology" in doc:
        return "ontology"
    return "model"


UNCODED_CODES = (("does not cover the primary key or a unique key",
                  "relationship/to-column-not-a-key"),)


def _as_diag(entry) -> dict:
    if isinstance(entry, _vendor.ValidationWarning):
        message = str(entry)
        code = next((c for needle, c in UNCODED_CODES if needle in message), None)
        diag = {"severity": "warning", "message": message}
        if code:
            diag["code"] = code
        return diag
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


SCHEMA_PATHS = {
    "model": "core-spec/ossie-schema.json",
    "ontology": "ontology/ontology.json",
    "mapping": "ontology/mapping.json",
}


def _load_schema(kind: str = "model"):
    """Load and metaschema-check a vendored schema; (schema, diag)."""
    path = VENDOR_DIR / SCHEMA_PATHS[kind]
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


def _dataset_fingerprint(dataset, alias_names=frozenset()):
    """Identity of a dataset that must match wherever the same name appears.

    Role logical sources point at ALIAS handles and are local to a document whose
    facts play that role, so they are excluded; everything else about a shared
    dimension must match, including its SCD shape and hierarchies.
    """
    fields = {}
    for field in dataset.get("fields") or []:
        if isinstance(field, dict) and field.get("name"):
            fields[field["name"]] = json.dumps(
                [field.get("expression"), field.get("datatype"), field.get("dimension")],
                sort_keys=True)
    payload = {}
    for data in (dataset.get("custom_extensions") or []):
        if isinstance(data, dict) and data.get("vendor_name") == "VIBEDATA":
            try:
                payload.update(json.loads(data.get("data") or "{}"))
            except json.JSONDecodeError:
                pass
    sources = {}
    for source in payload.get("logical_sources") or []:
        if not isinstance(source, dict):
            continue
        if source.get("physical_table") in alias_names:
            continue
        sources[source.get("name")] = json.dumps(
            [source.get("physical_table"), source.get("priority_group"),
             source.get("content_grain"), source.get("column_map"),
             source.get("content_levels"), source.get("content_filter"),
             source.get("navigable")],
            sort_keys=True)
    return {"source": dataset.get("source"),
            "primary_key": dataset.get("primary_key"),
            "unique_keys": dataset.get("unique_keys"),
            "fields": fields,
            "scd": payload.get("scd"),
            "levels": payload.get("levels"),
            "row_level": payload.get("row_level"),
            "hierarchies": payload.get("hierarchies"),
            "logical_sources": sources}


def _vibedata_of(node):
    """The decoded VIBEDATA payload on a node, version stripped; {} when absent or bad."""
    payload = {}
    for ext in node.get("custom_extensions") or []:
        if isinstance(ext, dict) and ext.get("vendor_name") == "VIBEDATA":
            try:
                decoded = json.loads(ext.get("data") or "{}")
            except json.JSONDecodeError:
                continue
            if isinstance(decoded, dict):
                payload.update(decoded)
    payload.pop("vibedata_version", None)
    return payload


def _supplied_through_inputs(metric, supplied):
    """A derived, time-series or dimension-rule metric is supplied when every input it reads is."""
    payload = _vibedata_of(metric)
    for key in ("time_series", "based_on_dimensions"):
        if isinstance(payload.get(key), dict):
            return payload[key].get("of") in supplied
    formula = payload.get("derived_expression")
    if isinstance(formula, str):
        try:
            names, _ = _names_in(formula)
        except ValueError:
            return False
        return bool(names) and names <= supplied
    return False


def cross_document_drift(docs):
    """Same name, different definition across documents: duplication that drifted.

    Shared dimensions are copied per star (relationships cannot cross documents),
    so a copy that disagrees with its twin is a silent second definition.
    """
    diags = []
    seen = {}
    for target, doc in docs:
        if not isinstance(doc, dict):
            continue
        aliases = frozenset(
            name for name, table in physical_table_index(doc).items()
            if table.get("table_type") == "ALIAS")
        for dataset in doc.get("datasets") or []:
            if isinstance(dataset, dict) and dataset.get("name"):
                seen.setdefault(("dataset", dataset["name"]), []).append(
                    (target, _dataset_fingerprint(dataset, aliases)))
        for metric in doc.get("metrics") or []:
            if isinstance(metric, dict) and metric.get("name"):
                seen.setdefault(("metric", metric["name"]), []).append(
                    (target, json.dumps([metric.get("expression"), _vibedata_of(metric)],
                                        sort_keys=True)))
        for name, table in physical_table_index(doc).items():
            seen.setdefault(("physical_table", name), []).append((target, table))
    for (kind, name), entries in seen.items():
        if len(entries) < 2:
            continue
        first_target, first = entries[0]
        for target, value in entries[1:]:
            if value != first:
                diags.append({
                    "severity": "error", "code": "crossdoc/diverged",
                    "message": f"{kind} '{name}' is defined differently in '{first_target}' "
                               f"and '{target}'; copies of a shared {kind} must match",
                    "file": target})
    return diags


@app.command()
def coverage(model: str, marts: str):
    """Every dbt model under MARTS must be named by a dbt_model; report both gaps."""
    docs = []
    for target in _resolve_targets(model):
        text, read_diag = _read_text(target)
        if read_diag:
            print(json.dumps([read_diag]))
            raise typer.Exit(1)
        docs.append((target, _vendor.load_yaml_named(text, str(target))))
    named = set()
    for _, doc in docs:
        for name, table in physical_table_index(doc).items():
            if table.get("dbt_model"):
                named.add(table["dbt_model"])
    on_disk = {path.stem for path in Path(marts).rglob("*.sql")}
    diags = [{"severity": "error", "code": "coverage/unmapped",
              "message": f"dbt model '{name}' is in the lakehouse but no dbt_model "
                         f"names it; register it or record why in a note"}
             for name in sorted(on_disk - named)]
    diags += [{"severity": "error", "code": "coverage/phantom",
               "message": f"dbt_model '{name}' names no file under {marts}"}
              for name in sorted(named - on_disk)]
    print(json.dumps(diags, indent=2))
    errors = [d for d in diags if d["severity"] == "error"]
    typer.echo(f"{len(on_disk)} model(s) on disk, {len(named)} named, "
               f"{len(errors)} coverage error(s).", err=True)
    raise typer.Exit(1 if errors else 0)


@app.command()
def suppliers(model: str):
    """Declared fields and metrics that no logical source supplies (content instrument)."""
    diags = []
    for target in _resolve_targets(model):
        text, read_diag = _read_text(target)
        if read_diag:
            diags.append(read_diag)
            continue
        doc = _vendor.load_yaml_named(text, str(target))
        supplied = set()
        for dataset in doc.get("datasets") or []:
            for ext in dataset.get("custom_extensions") or []:
                if ext.get("vendor_name") != "VIBEDATA":
                    continue
                try:
                    payload = json.loads(ext.get("data") or "{}")
                except json.JSONDecodeError:
                    continue
                for source in payload.get("logical_sources") or []:
                    supplied.update((source.get("column_map") or {}).keys())
            for field in dataset.get("fields") or []:
                if isinstance(field, dict) and field.get("name") not in supplied:
                    diags.append({"severity": "finding", "code": "suppliers/field",
                                  "file": str(target),
                                  "message": f"{dataset.get('name')}.{field['name']} is "
                                             "supplied by no logical source"})
        metrics = [m for m in doc.get("metrics") or [] if isinstance(m, dict)]
        grew = True
        while grew:  # inputs may themselves be derived
            grew = False
            for metric in metrics:
                if (metric.get("name") not in supplied
                        and _supplied_through_inputs(metric, supplied)):
                    supplied.add(metric["name"])
                    grew = True
        for metric in metrics:
            if metric.get("name") not in supplied:
                diags.append({"severity": "finding", "code": "suppliers/metric",
                              "file": str(target),
                              "message": f"metric '{metric['name']}' is supplied by no "
                                         "logical source"})
    print(json.dumps(diags, indent=2))
    typer.echo(f"{len(diags)} unsupplied item(s).", err=True)
    raise typer.Exit(1 if diags else 0)


POINTER = re.compile(r"held by\s+([A-Za-z_][A-Za-z0-9_]*)")
ADR_REF = re.compile(r"ADR (\d{4})")


@app.command()
def notes(model: str, tests: str, adr: str):
    """Every pointer a note carries must resolve: `held by <test>` and `ADR NNNN`."""
    diags = []
    tests_dir = Path(tests)
    adr_dir = Path(adr)
    for target in _resolve_targets(model):
        text, read_diag = _read_text(target)
        if read_diag:
            diags.append(read_diag)
            continue
        try:
            doc = _vendor.load_yaml_named(text, str(target))
        except Exception as e:  # noqa: BLE001 - report, never traceback
            diags.append({"severity": "error", "code": "cli/bad-yaml", "file": str(target),
                          "message": f"'{target}': invalid YAML: {e}"})
            continue
        for dataset in doc.get("datasets") or []:
            for source in _sources_of(dataset):
                note = source.get("note")
                if not note:
                    continue
                for name in POINTER.findall(note):
                    if not (tests_dir / f"{name}.sql").exists():
                        diags.append({"severity": "error", "code": "notes/dangling-test",
                                      "file": str(target),
                                      "message": f"{dataset.get('name')}.{source.get('name')} "
                                                 f"points at test '{name}', which is not "
                                                 f"{tests_dir}/{name}.sql"})
                for number in ADR_REF.findall(note):
                    if not list(adr_dir.glob(f"{number}-*.md")):
                        diags.append({"severity": "error", "code": "notes/dangling-adr",
                                      "file": str(target),
                                      "message": f"{dataset.get('name')}.{source.get('name')} "
                                                 f"cites ADR {number}, which has no file in "
                                                 f"{adr_dir}"})
    print(json.dumps(diags, indent=2))
    typer.echo(f"{len(diags)} dangling pointer(s).", err=True)
    raise typer.Exit(1 if diags else 0)


def _load_docs(model):
    docs = []
    for target in _resolve_targets(model):
        text, read_diag = _read_text(target)
        if read_diag:
            print(json.dumps([read_diag]))
            raise typer.Exit(1)
        docs.append(_vendor.load_yaml_named(text, str(target)))
    return docs


def _write_generated(sql, test_file, check, command):
    path = Path(test_file)
    if check:
        current = path.read_text() if path.exists() else None
        stale = current != sql
        print(json.dumps([{"severity": "error", "code": f"{command}/stale", "file": str(path),
                           "message": f"'{path}' is not what the model generates; run "
                                      f"{command} without --check"}] if stale else []))
        raise typer.Exit(1 if stale else 0)
    path.write_text(sql)
    print(json.dumps([]))
    typer.echo(f"wrote {path}", err=True)


@app.command("content-tests")
def content_tests(model: str, test_file: str,
                  check: bool = typer.Option(False, "--check",
                                             help="Exit 1 when TEST_FILE is not what MODEL generates")):
    """Write the dbt test that holds every aggregate binding to the detail (compiled SQL)."""
    try:
        sql = generate_content_tests(_load_docs(model))
    except CompileError as e:
        print(json.dumps([{"severity": "error", "code": "content-tests/compile",
                           "message": str(e)}]))
        raise typer.Exit(1) from e
    _write_generated(sql, test_file, check, "content-tests")


@app.command("columns")
def columns(model: str, catalog: str):
    """Every physical column the model names must exist in dbt's catalog.json."""
    path = Path(catalog)
    if not path.exists():
        print(json.dumps([{"severity": "error", "code": "columns/no-catalog",
                           "message": f"'{catalog}' does not exist; run `dbt docs generate` "
                                      "against a built warehouse first"}]))
        raise typer.Exit(1)
    known = catalog_relations(json.loads(path.read_text()))
    diags = []
    for target in _resolve_targets(model):
        text, read_diag = _read_text(target)
        if read_diag:
            diags.append(read_diag)
            continue
        diags.extend(check_columns(_vendor.load_yaml_named(text, str(target)), known, str(target)))
    print(json.dumps(diags, indent=2))
    typer.echo(f"{len(known)} relation(s) in the catalog, {len(diags)} unknown column(s).",
               err=True)
    raise typer.Exit(1 if diags else 0)


@app.command("compile")
def compile_command(model: str, query_file: str):
    """Compile a semantic query (YAML or JSON) against one model document; print JSON."""
    docs = _load_docs(model)
    if len(docs) != 1:
        print(json.dumps([{"severity": "error", "code": "compile/one-document",
                           "message": "compile reads exactly one model document"}]))
        raise typer.Exit(1)
    query = Query.from_dict(_vendor.load_yaml_named(Path(query_file).read_text(), query_file))
    try:
        result = compile_query(Model(docs[0], lambda t: t["source"]), query)
    except CompileError as e:
        print(json.dumps([{"severity": "error", "code": "compile/error", "message": str(e)}]))
        raise typer.Exit(1) from e
    print(json.dumps({"source": result.source, "columns": result.columns,
                      "rejected": result.rejected, "sql": result.sql}, indent=2))


@app.command("level-tests")
def level_tests(model: str, test_file: str,
                check: bool = typer.Option(False, "--check",
                                           help="Exit 1 when TEST_FILE is not what MODEL generates")):
    """Write the dbt test that reports data departing from the declared levels."""
    sql = generate_level_tests(_load_docs(model))
    _write_generated(sql, test_file, check, "level-tests")


def _sources_of(dataset):
    if not isinstance(dataset, dict):
        return
    for ext in dataset.get("custom_extensions") or []:
        if not isinstance(ext, dict) or ext.get("vendor_name") != "VIBEDATA":
            continue
        try:
            payload = json.loads(ext.get("data") or "{}")
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        for source in payload.get("logical_sources") or []:
            if isinstance(source, dict):
                yield source


DECLARATION_KEYS = ("requires", "derived_by")


def _walk(node):
    """Every dict in a document tree, whatever shape the caller's schema allows."""
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk(value)


def _declaration_warnings(data) -> list:
    """Report hidden semantics: fields that look executable and are not."""
    used = sorted({
        key for node in _walk(data) for key in DECLARATION_KEYS
        if node.get(key)
    })
    if data.get("prefixes"):
        used.append("prefixes")
    if data.get("custom_extensions"):
        used.append("custom_extensions")
    if not used:
        return []
    return [{"severity": "warning", "code": "declaration-only",
             "message": f"uses {', '.join(used)}, which no evaluator reads; this document is "
                        f"declaration-only and must not be described as executable"}]


def ontology_checks(data) -> list:
    """Checks the ontology schema cannot make: identity is declared, semantics are prose."""
    diags = []
    for component in data.get("ontology") or []:
        if not isinstance(component, dict):
            continue
        if component.get("type") == "EntityType" and not component.get("identify_by"):
            diags.append({"severity": "error", "code": "ontology/no-identity",
                          "message": f"EntityType '{component.get('concept')}' has no "
                                     f"identify_by; identity is a declared relationship to a "
                                     f"value type, never a surrogate"})
    return diags + _declaration_warnings(data)


def _load_docs(directory: Path, suffix: str):
    """Yield (path, document, diag) for every document of one kind in a directory."""
    for path in sorted(directory.glob(f"*{suffix}")):
        text, read_diag = _read_text(path)
        if read_diag:
            yield path, None, read_diag
            continue
        try:
            yield path, _vendor.load_yaml_named(text, str(path)), None
        except Exception as e:  # noqa: BLE001 - report, never traceback
            yield path, None, {"severity": "error", "code": "cli/bad-yaml",
                               "file": str(path),
                               "message": f"'{path}': invalid YAML: {e}"}


DATASET_FIELD = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\s*$")


@app.command()
def refs(ontology: str, model: str):
    """Every mapping ref resolves; every expression names a declared dataset.field."""
    ont_dir, model_dir = Path(ontology), Path(model)
    diags = []
    ontologies, models, model_files, mappings = {}, {}, {}, []
    for path, doc, diag in _load_docs(ont_dir, ONTOLOGY_SUFFIX):
        if diag:
            diags.append(diag)
        else:
            ontologies[doc.get("name")] = doc
    for path, doc, diag in _load_docs(model_dir, MODEL_SUFFIX):
        if diag:
            diags.append(diag)
        else:
            models[doc.get("name")] = doc
            model_files[doc.get("name")] = str(path)
    for path, doc, diag in _load_docs(ont_dir, MAPPING_SUFFIX):
        if diag:
            diags.append(diag)
        else:
            mappings.append((path, doc))

    mapped = set()
    for path, doc in mappings:
        file = str(path)
        model_name = (doc.get("semantic_model_ref") or {}).get("name")
        ontology_name = (doc.get("ontology_ref") or {}).get("name")
        referenced_model = models.get(model_name)
        referenced_ontology = ontologies.get(ontology_name)
        if referenced_model is None:
            diags.append({"severity": "error", "code": "mapping/unresolved-ref", "file": file,
                          "message": f"semantic_model_ref '{model_name}' matches no document "
                                     f"name in {model_dir}"})
        else:
            mapped.add(model_name)
        if referenced_ontology is None:
            diags.append({"severity": "error", "code": "mapping/unresolved-ref", "file": file,
                          "message": f"ontology_ref '{ontology_name}' matches no document "
                                     f"name in {ont_dir}"})
            continue
        concepts = {component.get("concept") for component in
                    referenced_ontology.get("ontology") or [] if isinstance(component, dict)}
        relationships = {relationship.get("name") for component in
                         referenced_ontology.get("ontology") or [] if isinstance(component, dict)
                         for relationship in component.get("relationships") or []
                         if isinstance(relationship, dict)}
        declared = {(dataset.get("name"), field.get("name"))
                    for dataset in (referenced_model or {}).get("datasets") or []
                    if isinstance(dataset, dict)
                    for field in dataset.get("fields") or [] if isinstance(field, dict)}
        for node in _walk(doc.get("concept_mappings") or []):
            concept = node.get("concept")
            if concept and concept not in concepts:
                diags.append({"severity": "error", "code": "mapping/unknown-concept",
                              "file": file, "message": f"maps concept '{concept}', which "
                                                        f"'{ontology_name}' does not declare"})
            relationship = node.get("relationship")
            if relationship and relationship not in relationships:
                diags.append({"severity": "error", "code": "mapping/unknown-relationship",
                              "file": file, "message": f"maps relationship '{relationship}', "
                                                        f"which '{ontology_name}' does not declare"})
            expression = node.get("expression")
            if not expression:
                continue
            match = DATASET_FIELD.match(str(expression))
            if not match:
                diags.append({"severity": "error", "code": "mapping/unqualified-expression",
                              "file": file, "message": f"expression '{expression}' is not "
                                                        f"dataset.field, so it cannot be checked"})
            elif match.groups() not in declared:
                diags.append({"severity": "error", "code": "mapping/unknown-field",
                              "file": file, "message": f"expression '{expression}' names no "
                                                        f"dataset.field that '{model_name}' "
                                                        f"declares"})

    for name in sorted(set(models) - mapped):
        diags.append({"severity": "warning", "code": "mapping/none",
                      "file": model_files[name],
                      "message": f"model '{name}' has no mapping; each document is mapped or "
                                 f"its description says why no concept reaches it"})
    print(json.dumps(diags, indent=2))
    errors = [d for d in diags if d["severity"] == "error"]
    warnings = [d for d in diags if d["severity"] == "warning"]
    typer.echo(f"{len(mappings)} mapping(s), {len(errors)} error(s), "
               f"{len(warnings)} warning(s). Declaration-only: no expression is executed.",
               err=True)
    raise typer.Exit(1 if errors else 0)


TERM_HEADING = re.compile(r"^\*\*([^*]+)\*\*:", re.MULTILINE)


@app.command()
def glossary(ontology: str, context: str):
    """Every EntityType names a glossary term; terms with no concept are listed."""
    diags = []
    text, read_diag = _read_text(Path(context))
    if read_diag:
        diags.append(read_diag)
        terms = {}
    else:
        terms = {name.strip().casefold(): name.strip()
                 for name in TERM_HEADING.findall(text)}
    concepts = {}
    for path, doc, diag in _load_docs(Path(ontology), ONTOLOGY_SUFFIX):
        if diag:
            diags.append(diag)
            continue
        for component in doc.get("ontology") or []:
            if isinstance(component, dict) and component.get("concept"):
                concepts[component["concept"]] = component.get("type")

    for name, kind in sorted(concepts.items()):
        if kind == "EntityType" and name.casefold() not in terms:
            diags.append({"severity": "error", "code": "glossary/concept-untraced",
                          "message": f"concept '{name}' has no '**{name}**:' term in {context}"})
    represented = {name.casefold() for name in concepts}
    for key, shown in sorted(terms.items()):
        if key not in represented:
            diags.append({"severity": "finding", "code": "glossary/term-unrepresented",
                          "message": f"term '{shown}' has no concept; add one if it denotes a "
                                     f"thing with identity, otherwise it is a rule or measure "
                                     f"and stays prose"})
    print(json.dumps(diags, indent=2))
    errors = [d for d in diags if d["severity"] == "error"]
    findings = [d for d in diags if d["severity"] == "finding"]
    typer.echo(f"{len(concepts)} concept(s), {len(errors)} error(s), "
               f"{len(findings)} term(s) with no concept.", err=True)
    raise typer.Exit(1 if errors else 0)


@app.command()
def dimensionality(model: str):
    """Per metric: its facts and the dimensions a query may group or filter it by.

    Engines and exporters read this to reject a query that groups a metric by a
    dimension it cannot reach (unrelated_dimensions: error) or to repeat its total there.
    """
    out = {}
    for target in _resolve_targets(model):
        text, read_diag = _read_text(target)
        if read_diag:
            print(json.dumps([read_diag]))
            raise typer.Exit(1)
        doc = _vendor.load_yaml_named(text, str(target))
        out[doc.get("name", str(target))] = metric_dimensionality(doc)
    print(json.dumps(out, indent=2))


@app.command()
def validate(model: str):
    """Validate canonical file(s): schema, then the pass that kind allows."""
    targets = _canonical_targets(model)
    if not targets:
        print(json.dumps([{"severity": "error", "code": "cli/no-files",
                           "message": f"No {' / '.join('*' + s for s in SUFFIXES)} under "
                                      f"'{model}'"}]))
        raise typer.Exit(1)
    schemas = {}
    diags = []
    parsed_models = []
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
        kind = _kind(data)
        if kind not in schemas:
            schemas[kind] = _load_schema(kind)
        schema, schema_diag = schemas[kind]
        if schema_diag:
            schema_diag["file"] = str(target)
            diags.append(schema_diag)
            continue
        try:
            file_diags = [_as_diag(e) for e in _vendor.validate_document(data, schema)]
            if not any(d["severity"] == "error" for d in file_diags):
                if kind == "model":
                    file_diags.extend(validate_vibedata(data))
                elif kind == "ontology":
                    file_diags.extend(ontology_checks(data))
                else:
                    file_diags.extend(_declaration_warnings(data))
        except Exception as e:  # noqa: BLE001 - a check bug must not kill JSON output
            file_diags = [{"severity": "error", "code": "cli/check-crashed",
                           "message": f"'{target}': validator crashed: {type(e).__name__}: {e}"}]
        for d in file_diags:
            d.setdefault("file", str(target))
        diags.extend(file_diags)
        if kind == "model":
            parsed_models.append((str(target), data))
    if len(parsed_models) > 1:
        diags.extend(cross_document_drift(parsed_models))
    if Path(model).is_dir():
        for path in sorted(Path(model).glob("*.y*ml")):
            if not path.name.endswith(SUFFIXES):
                diags.append({"severity": "error", "code": "cli/unmatched-file",
                              "file": str(path),
                              "message": f"'{path}' is not one of "
                                         f"{', '.join('*' + s for s in SUFFIXES)}; "
                                         f"rename it or move it out of the directory"})
    print(json.dumps(diags, indent=2))
    errors = [d for d in diags if d["severity"] == "error"]
    warnings = [d for d in diags if d["severity"] == "warning"]
    typer.echo(f"{len(targets)} file(s), {len(errors)} error(s), "
               f"{len(warnings)} warning(s). Structural check only — content review is the "
               f"validating-semantic-model skill.", err=True)
    raise typer.Exit(1 if errors else 0)


if __name__ == "__main__":
    app()

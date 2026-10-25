"""ODCS data-contract tooling for this repo.

Commands: `check` (schema and structure of the committed contracts, and their agreement
with the canonical model that names each gold relation), `check --relations` (adds the
comparison against the built relation), `reverse` (draft contracts from an existing
warehouse, with the questions neither the warehouse nor the model can settle), `generate`
(write the dbt keys and dlt hints from the contracts).

This script proves shape and reports facts. It never judges meaning: the grain, whether a
`required` is honest, and whether a quality rule encodes the real business answer are the
`validating-data-contract` review, not a pass/fail here.

Every location resolves from `repo-map.json`: a layer's `path` for the dbt models it builds,
the seeds layer for its CSVs, and a source's `docs` file for the resources it lands. The
warehouse is consulted only by `--relations`.

Usage:
  python3 scripts/odcs.py check [--root PATH] [--relations]
  python3 scripts/odcs.py reverse [--root PATH] [--catalog PATH]
  python3 scripts/odcs.py generate [--root PATH]

JSON diagnostics go to stdout (agent-parseable); human prose to stderr.
Exit 0 when no errors (warnings allowed), 1 otherwise.
"""

import json
import ast
import os
import re
import uuid
from pathlib import Path

import duckdb
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

# Ossie `DataType` reduced to the ODCS `logicalType` it states; `Opaque` states none.
LOGICAL_TYPES = {
    "String": "string",
    "Integer": "integer",
    "Decimal": "number",
    "Float": "number",
    "Boolean": "boolean",
    "Date": "date",
    "Time": "time",
    "DateTime": "timestamp",
    "DateTimeTz": "timestamp",
    "Opaque": None,
}

# dbt reads a model's properties under `models:` and a seed's under `seeds:`.
PROPERTIES_SECTION = {"model": "models", "seed": "seeds"}

# Relations the installed loader library writes into every dlt schema; no dlt resource declares
# them, and nothing is generated from their contracts.
AUDIT_RELATIONS = ("audit_runs", "audit_table_loads")

# The warehouse file at the repo root: what `servers[].database` names and what `reverse` reads
# when no catalog is given.
WAREHOUSE_FILE = "domain.duckdb"

# A DuckDB column type reduced to the ODCS `logicalType` that states the same value.
PHYSICAL_LOGICAL = {
    "VARCHAR": "string",
    "CHAR": "string",
    "TEXT": "string",
    "STRING": "string",
    "UUID": "string",
    "JSON": "string",
    "BIGINT": "integer",
    "INTEGER": "integer",
    "SMALLINT": "integer",
    "TINYINT": "integer",
    "HUGEINT": "integer",
    "UBIGINT": "integer",
    "UINTEGER": "integer",
    "USMALLINT": "integer",
    "UTINYINT": "integer",
    "DECIMAL": "number",
    "DOUBLE": "number",
    "FLOAT": "number",
    "REAL": "number",
    "BOOLEAN": "boolean",
    "DATE": "date",
    "TIME": "time",
    "TIMESTAMP": "timestamp",
    "TIMESTAMP WITH TIME ZONE": "timestamp",
    "TIMESTAMP_NS": "timestamp",
    "TIMESTAMP_MS": "timestamp",
    "TIMESTAMP_S": "timestamp",
}

# A dbt generic test as the ODCS library rule it asserts. A `relationships` test is not a rule:
# it becomes the property's `relationships[]` entry instead.
RULE_METRICS = {"not_null": "nullValues", "unique": "duplicateValues",
                "accepted_values": "invalidValues"}

# A dbt `relationships` test names its target as a rendered reference.
REF_REFERENCE = re.compile(r"ref\(\s*['\"]([^'\"]+)['\"]\s*\)")
SOURCE_REFERENCE = re.compile(r"source\(\s*['\"][^'\"]+['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*\)")

# What `reverse` could not settle, queued for the review instead of guessed. A finding is a
# warning: the tool reports the doubt and the run still succeeds.
NO_GRAIN = "finding/no-grain"
UNDESCRIBED = "finding/undescribed"
UNPROVEN_NULLABLE = "finding/unproven-nullable"
KEY_REPEATS = "finding/key-repeats"
OPEN_ENUM = "finding/open-enum"
UNDECLARED_FOREIGN_KEY = "finding/undeclared-foreign-key"

# A name that reads as the relation's own key, and one that reads as a reference to another
# relation's. The shape is the evidence; only a declaration or the data can settle it.
KEY_SHAPED = re.compile(r"_(key|natural_key)$")
REFERENCE_SHAPED = re.compile(r"_(key|id)$")

# At most this many distinct values is the shape of an enum; above it a column reads as free
# text, a name or a code. A judgement, stated here so a review can argue with the number.
ENUM_MAX_DISTINCT = 12

# Authored once, for the relations no declared resource in this repo builds.
AUDIT_PURPOSE = (
    "Load audit relation, owned by the installed vibedata library. The loader writes its "
    "columns, so a change here follows a loader upgrade rather than a change in this "
    "repository's sources."
)

# Files that carry sources, unit tests or semantics; a generated key has no home in them.
RESERVED_PROPERTIES = ("_sources.yml", "_unit_tests.yml", "_semantic.yml")

# A DuckDB physical type reduced to the dlt column type that lands the same value.
DLT_TYPES = {
    "VARCHAR": "text",
    "DOUBLE": "double",
    "DECIMAL": "decimal",
    "BIGINT": "bigint",
    "INTEGER": "bigint",
    "HUGEINT": "bigint",
    "BOOLEAN": "bool",
    "DATE": "date",
    "TIMESTAMP": "timestamp",
    "TIMESTAMP WITH TIME ZONE": "timestamp",
}

# The quality metrics that reduce to a generic dbt test, and the test each becomes.
QUALITY_TESTS = {"duplicateValues": "unique", "nullValues": "not_null"}

app = typer.Typer(add_completion=False)


def _diag(severity: str, code: str, message: str) -> dict:
    return {"severity": severity, "code": code, "message": message}


class _Refused(Exception):
    """A contract the tool will not write from, carrying the diagnostic that says why."""

    def __init__(self, diag: dict):
        super().__init__(diag["message"])
        self.diag = diag


class _IndentedDumper(yaml.SafeDumper):
    """PyYAML puts a block sequence flush with its key; this repo's YAML indents it."""

    def increase_indent(self, flow: bool = False, indentless: bool = False):
        return super().increase_indent(flow, False)


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
    resource docs. The loader's audit relations are written by the installed library and appear
    in none of these, so only the catalog can see them: `reverse` contracts them and `check`
    refuses to call their contracts orphans.
    """
    expected: dict[tuple[str, str], str] = {}
    for name, layer in (repo_map.get("layers") or {}).items():
        path = root / layer["path"] if layer.get("path") else None
        if path is None or not path.is_dir() or layer.get("built_by") != "dbt":
            continue
        # A dbt layer builds whatever it holds: a model from a `.sql`, a seed from a `.csv`.
        # Which suffix belongs to which is the file's fact, not the layer's name.
        for suffix in (".sql", ".csv"):
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


def _committed_contracts(root: Path, repo_map: dict) -> dict[tuple[str, str], Path]:
    """Every committed contract, or a refusal when the map declares no place to keep them."""
    if not (repo_map.get("artifact_paths") or {}).get("data_contract"):
        raise _Refused(_diag(
            "error", "contract/unconfigured",
            "repo-map.json declares no artifact_paths.data_contract, so no contract can be found",
        ))
    return _contract_relations(root, repo_map)


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


def _prose(text: object) -> str | None:
    """One flowing line, or nothing when there is no prose to state.

    `{{ doc("...") }}` is a pointer dbt resolves at parse time, not a description; a contract
    that copied it would carry syntax no reader or tool outside dbt can turn into an answer.
    """
    value = " ".join(str(text).split()) if text is not None else ""
    if not value or "{{" in value:
        return None
    return value


def _grain(doc: dict, path: Path) -> list[dict]:
    """A warning, not an error: an onboarding run may leave the grain to review."""
    elements = [e for e in (doc.get("schema") or []) if isinstance(e, dict)]
    stated = [e for e in elements if _prose(e.get("dataGranularityDescription"))]
    if stated:
        return []
    return [_diag("warning", "contract/no-grain",
                  f"{path}: no `dataGranularityDescription`; the review refuses a contract "
                  f"a shipped intent presents as complete without one")]


def _canonical_datasets(root: Path, repo_map: dict) -> dict[tuple[str, str], tuple[dict, Path]]:
    """Every dataset the canonical model declares, keyed by the relation its `source` names.

    Each value keeps the document it was read from, so a contract can name its authority and
    the two readings cannot disagree. Empty when the repo has adopted no canonical model: a
    contract set is not broken for lacking something it never promised to agree with.
    """
    raw = (repo_map.get("artifact_paths") or {}).get("logical_model")
    if not raw:
        return {}
    base = _declared(root, raw)
    datasets: dict[tuple[str, str], tuple[dict, Path]] = {}
    if not base.is_dir():
        return datasets
    for path in sorted(base.glob("*.ossie.yaml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for dataset in doc.get("datasets") or []:
            if not isinstance(dataset, dict):
                continue
            source = str(dataset.get("source") or "").split(".", 1)
            if len(source) == 2:
                datasets[(source[0], source[1])] = (dataset, path)
    return datasets


def _gold_schemas(repo_map: dict, expected: dict[tuple[str, str], str]) -> set[str]:
    """Schemas holding gold relations: the layers the map declares gold, where they are built.

    The map is the only source. Another Domain names its layers differently, so a layer name is
    something this tool cannot know; guessing one — by exclusion, or by the shape of the
    directory — would gate relations the Domain never called gold and pass over the ones it did.
    An undeclared set is therefore empty and names nothing, and `check` warns about the gap
    instead of inventing a gold set to fill it.
    """
    layers = repo_map.get("layers") or {}
    built = {schema for schema, _ in expected}
    return {
        layers[name]["schema"]
        for name in repo_map.get("gold_layers") or []
        if name in layers and layers[name]["schema"] in built
    }


def _properties(contract: dict) -> dict[str, dict]:
    """The contract's properties by name, across every schema element."""
    props: dict[str, dict] = {}
    for element in contract.get("schema") or []:
        if isinstance(element, dict):
            for prop in element.get("properties") or []:
                if isinstance(prop, dict) and prop.get("name"):
                    props[prop["name"]] = prop
    return props


def _property_diagnostics(where: str, prop: dict, field: dict, primary: bool) -> list[dict]:
    """One contract property against the model field the document declares for it.

    Only the model's own declarations are compared: it is curated, so a property it never
    names is the contract's business.
    """
    diags = []
    datatype = field.get("datatype")
    if datatype in LOGICAL_TYPES:
        want = LOGICAL_TYPES[datatype]
        got = prop.get("logicalType")
        if got != want:
            diags.append(_diag("error", "gold/divergent",
                               f"{where}: logicalType is {got!r}, the canonical model's "
                               f"{datatype} is {want!r}"))
        zone = (prop.get("logicalTypeOptions") or {}).get("timezone")
        if datatype == "DateTimeTz" and not zone:
            diags.append(_diag("error", "gold/divergent",
                               f"{where}: `{datatype}` needs logicalTypeOptions.timezone true"))
        elif datatype == "DateTime" and zone:
            diags.append(_diag("error", "gold/divergent",
                               f"{where}: `{datatype}` must not carry logicalTypeOptions.timezone"))
    if primary and prop.get("primaryKey") is not True:
        diags.append(_diag("error", "gold/divergent",
                           f"{where}: the canonical model declares this primary key and the "
                           f"property does not set primaryKey true"))
    return diags


def _loader_columns(relation: tuple[str, str], contract: dict, repo_map: dict) -> list[dict]:
    """A raw relation's contract declares no `_dlt_*` column: dlt adds those to the table.

    A dbt model is the exception and the reason for the distinction: its enforced contract must
    declare every output column, so a model that selects the loader's column keeps it.
    """
    if _is_dbt(relation, repo_map):
        return []
    return [
        _diag("error", "contract/loader-column",
              f"{relation[0]}.{relation[1]}: `{name}` is a column the loader adds to a "
              f"dlt-loaded relation, not one the relation yields")
        for name in sorted(_properties(contract))
        if name.startswith("_dlt")
    ]


def _gold_agreement(relation: tuple[str, str], path: Path, contract: dict,
                    documents: dict[tuple[str, str], tuple[dict, Path]],
                    gold: set[str]) -> list[dict]:
    """A gold contract against the canonical document that names its relation."""
    label = f"{relation[0]}.{relation[1]}"
    declared_document = documents.get(relation)
    if declared_document is None:
        if relation[0] not in gold:
            return []
        return [_diag("error", "gold/undeclared",
                      f"{path}: no canonical document names the gold relation {label}")]
    dataset = declared_document[0]
    declared = {
        field["name"]: field
        for field in dataset.get("fields") or []
        if isinstance(field, dict) and field.get("name")
    }
    keys = set(dataset.get("primary_key") or [])
    props = _properties(contract)
    diags = []
    for name, field in declared.items():
        prop = props.get(name)
        if prop is None:
            diags.append(_diag("error", "gold/omits-declared",
                               f"{label}: the contract omits `{name}`, which the canonical "
                               f"model declares"))
        else:
            diags.extend(_property_diagnostics(f"{label}.{name}", prop, field, name in keys))
    diags.extend(_declared_relationships(relation, path, dataset, props, documents,
                                        declared_document[1]))
    diags.extend(_declared_unique_keys(label, dataset))
    return diags


def _declared_relationships(relation: tuple[str, str], path: Path, dataset: dict,
                            props: dict[str, dict],
                            documents: dict[tuple[str, str], tuple[dict, Path]],
                            document_path: Path) -> list[dict]:
    """Every relationship the document declares FROM this dataset, against the contract.

    The document states the identity graph; a contract that drops a relationship publishes a
    shape a consumer cannot join on, and nothing else compares the two.
    """
    targets = {
        str(doc.get("name")): str(doc.get("source")).split(".", 1)[-1]
        for doc, _path in documents.values()
        if doc.get("name") and doc.get("source")
    }
    document = yaml.safe_load(document_path.read_text(encoding="utf-8")) or {}
    diags = []
    for relationship in document.get("relationships") or []:
        if relationship.get("from") != dataset.get("name"):
            continue
        target = targets.get(str(relationship.get("to")))
        columns = relationship.get("to_columns") or []
        if target is None or not columns:
            continue
        for column in relationship.get("from_columns") or []:
            prop = props.get(column)
            if prop is None:
                continue
            declared = [
                str(entry.get("to") or "").split(".")
                for entry in prop.get("relationships") or []
                if isinstance(entry, dict)
            ]
            if not any(parts and parts[-1] == columns[0] and target in parts for parts in declared):
                diags.append(_diag(
                    # A warning: carrying the edge publishes a shape and adds a dbt test, so
                    # authoring it is a deliberate change, not a gate fix. Reported, never silent.
                    "warning", "gold/missing-relationship",
                    f"{relation[0]}.{relation[1]}.{column}: the canonical model declares "
                    f"`{relationship.get('name')}` to `{target}.{columns[0]}` and the contract "
                    f"declares no such relationship",
                ))
    return diags


def _declared_unique_keys(label: str, dataset: dict) -> list[dict]:
    """A composite unique key is a promise ODCS cannot state: report it, never drop it.

    A warning, because the contract has no field for a multi-column key: `unique` is per
    property. Saying nothing would lose the key; failing would demand an inexpressible fix.
    """
    diags = []
    for key in dataset.get("unique_keys") or []:
        if not isinstance(key, list) or len(key) < 2:
            continue
        diags.append(_diag(
            "warning", "gold/composite-key",
            f"{label}: the canonical model declares the composite unique key "
            f"({', '.join(str(k) for k in key)}); ODCS states uniqueness per property, so the "
            f"contract cannot carry it and a reader needs the document",
        ))
    return diags


def _layer_for(repo_map: dict, schema: str) -> dict | None:
    """The layer that declares a schema; the map is the only place a schema is named."""
    for layer in (repo_map.get("layers") or {}).values():
        if layer.get("schema") == schema:
            return layer
    return None


def _is_dbt(relation: tuple[str, str], repo_map: dict) -> bool:
    """Whether a dbt layer builds the relation, as opposed to a dlt pipeline or the loader."""
    layer = _layer_for(repo_map, relation[0])
    return layer is not None and layer.get("built_by") == "dbt"


def _is_loader_column(relation: tuple[str, str], name: str, repo_map: dict) -> bool:
    """A `_dlt_*` column dlt adds to a relation it loaded.

    A dbt model that selects the column propagates it deliberately, and its enforced contract
    must declare every output column, so only a raw relation excludes the loader's own.
    """
    return name.startswith("_dlt") and not _is_dbt(relation, repo_map)


def _is_audit(relation: tuple[str, str], repo_map: dict) -> bool:
    """A relation the installed loader writes into a dlt layer's schema, not a dlt resource."""
    layer = _layer_for(repo_map, relation[0])
    return (
        layer is not None
        and layer.get("built_by") == "dlt"
        and relation[1] in AUDIT_RELATIONS
    )


def _hints_module(root: Path, repo_map: dict) -> Path:
    """`contracts.py` under the ingestion root the map declares."""
    raw = (repo_map.get("artifact_paths") or {}).get("ingestion_root")
    if not raw:
        raise _Refused(_diag("error", "contract/unconfigured",
                             "repo-map.json declares no artifact_paths.ingestion_root, so no "
                             "dlt hints module can be placed"))
    return _declared(root, raw) / "contracts.py"


def _properties_file(root: Path, layer: dict, table: str, section: str) -> Path:
    """The layer file that already names this relation, or the one this tool creates."""
    directory = root / layer["path"]
    if directory.is_dir():
        for path in sorted(directory.glob("*.yml")) + sorted(directory.glob("*.yaml")):
            if path.name in RESERVED_PROPERTIES:
                continue
            try:
                doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            except (yaml.YAMLError, OSError):
                continue
            if _document_entry(doc, section, table) is not None:
                return path
    return directory / "_generated.yml"


def _document_entry(doc: dict, section: str, table: str) -> dict | None:
    """The properties entry named `table` under `section`."""
    for entry in doc.get(section) or []:
        if isinstance(entry, dict) and entry.get("name") == table:
            return entry
    return None


def _target(root: Path, repo_map: dict, relation: tuple[str, str]) -> tuple[str, Path] | None:
    """What kind of relation this is and which generated artifact its keys belong to."""
    if _is_audit(relation, repo_map):
        return None
    layer = _layer_for(repo_map, relation[0])
    if layer is None:
        return None
    if layer.get("built_by") == "dlt":
        return "dlt", _hints_module(root, repo_map)
    kind = "seed" if (root / layer["path"] / f"{relation[1]}.csv").is_file() else "model"
    return kind, _properties_file(root, layer, relation[1], PROPERTIES_SECTION[kind])


def _dlt_type(physical: str) -> str | None:
    """A DuckDB type reduced to the dlt column type that lands the same value."""
    return DLT_TYPES.get(physical.split("(", 1)[0].strip().upper())


def _relationship_test(where: str, to: str) -> dict:
    """One declared property relationship as the dbt test that enforces it.

    dbt resolves a target by `ref()`, which names a model rather than a schema-qualified
    relation, so `core.dim_zone.zone_key` and `dim_zone.zone_key` both name `dim_zone`.
    """
    relation, _, field = str(to).rpartition(".")
    table = relation.rpartition(".")[2]
    if not table or not field:
        raise _Refused(_diag("error", "contract/unmapped-relationship",
                             f"{where}: `to: {to}` names no `<relation>.<column>`"))
    return {"relationships": {"arguments": {"to": f"ref('{table}')", "field": field}}}


def _data_tests(prop: dict, where: str) -> list:
    """The generic dbt tests a property's quality rules and relationships reduce to."""
    tests: list = []
    for rule in prop.get("quality") or []:
        if not isinstance(rule, dict) or rule.get("type") != "library":
            continue
        if rule.get("mustBe") != 0:
            continue
        metric = rule.get("metric")
        if metric in QUALITY_TESTS:
            if QUALITY_TESTS[metric] not in tests:
                tests.append(QUALITY_TESTS[metric])
        elif metric == "invalidValues":
            values = (rule.get("arguments") or {}).get("valid_values")
            if values and not any(isinstance(test, dict) for test in tests):
                tests.append({"accepted_values": {"arguments": {"values": values}}})
    for relationship in prop.get("relationships") or []:
        declared = relationship if isinstance(relationship, dict) else {}
        tests.append(_relationship_test(where, declared.get("to")))
    return tests


def _owned(relation: tuple[str, str], contract: dict, kind: str) -> dict:
    """The keys `generate` owns for one contract, and nothing else.

    A model carries the enforced contract, a `data_type` per property and the `data_tests` its
    rules reduce to; a seed carries only the generated tests, since dbt's contract is
    model-only; a dlt table carries its hints. A key the contract cannot ground is a refusal,
    never a guess.
    """
    for server in contract.get("servers") or []:
        stated = (server or {}).get("schema") if isinstance(server, dict) else None
        if stated and stated != relation[0]:
            raise _Refused(_diag("error", "servers/mismatch",
                                 f"{relation[0]}.{relation[1]}: `servers[].schema` says "
                                 f"{stated!r}, the map declares {relation[0]!r}"))
    owned: dict = {"columns": {}}
    if kind == "model":
        owned["contract"] = {"enforced": True}
    for name, prop in _properties(contract).items():
        where = f"{relation[0]}.{relation[1]}.{name}"
        keys: dict = {}
        if kind == "seed":
            tests = _data_tests(prop, where)
            if not tests:
                continue
            keys["data_tests"] = tests
        else:
            physical = str(prop.get("physicalType") or "").strip()
            if kind == "dlt":
                mapped = _dlt_type(physical) if physical else None
                if mapped is None:
                    raise _Refused(_diag("error", "contract/unmapped-type",
                                         f"{where}: `{physical or 'no physicalType'}` has no dlt "
                                         f"column type"))
                keys["data_type"] = mapped
                keys["nullable"] = not prop.get("required", False)
            elif physical:
                keys["data_type"] = physical
            else:
                raise _Refused(_diag("error", "contract/unmapped-type",
                                     f"{where}: no `physicalType`, so no dbt `data_type`"))
            if kind == "model":
                tests = _data_tests(prop, where)
                if tests:
                    keys["data_tests"] = tests
        owned["columns"][name] = keys
    return owned


ITEM = re.compile(r"^(\s*)- name:\s*(.+?)\s*$")
KEY = re.compile(r"^(\s*)([A-Za-z_][\w-]*):\s*(.*)$")


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _block_end(lines: list[str], index: int, indent: int) -> int:
    """The line after the block that the `- name:` line at `indent` opens: a sibling ends it."""
    for other in range(index + 1, len(lines)):
        text = lines[other].strip()
        if text and not text.startswith("#") and _indent(lines[other]) <= indent:
            return other
    return len(lines)


def _key_block_end(lines: list[str], index: int, indent: int) -> int:
    """The line after the value of the key at `indent`.

    A block sequence may sit at the same indent as the key that owns it, so a `- ` line there
    is the value; the next mapping key is what ends it.
    """
    for other in range(index + 1, len(lines)):
        text = lines[other].strip()
        if not text or text.startswith("#"):
            continue
        if _indent(lines[other]) < indent:
            return other
        if _indent(lines[other]) == indent and not text.startswith("-"):
            return other
    return len(lines)


def _content_end(lines: list[str], start: int, end: int) -> int:
    """The span without its trailing blank lines."""
    while end > start and not lines[end - 1].strip():
        end -= 1
    return end


def _section(lines: list[str], key: str) -> tuple[int, int] | None:
    """The line span that a top-level `key:` opens."""
    for index, line in enumerate(lines):
        match = KEY.match(line)
        if match and _indent(line) == 0 and match.group(2) == key and not match.group(3):
            return index + 1, _key_block_end(lines, index, 0)
    return None


def _entry(lines: list[str], name: str, lo: int, hi: int) -> tuple[int, int] | None:
    """The `- name: <name>` item inside lines[lo:hi]."""
    for index in range(lo, hi):
        match = ITEM.match(lines[index])
        if match and _scalar(match.group(2)) == name:
            return index, _block_end(lines, index, len(match.group(1)))
    return None


def _scalar(text: str):
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError:
        return text


def _key_indent(lines: list[str], start: int, end: int) -> int:
    """The indent of the mapping keys belonging to the item that starts at `start`."""
    for index in range(start + 1, end):
        if lines[index].strip() and not lines[index].lstrip().startswith("#"):
            return _indent(lines[index])
    return _indent(lines[start]) + 2


def _key_span(lines: list[str], start: int, end: int, key: str) -> tuple[int, int] | None:
    """(line, span end) of `key:` among the item's own keys."""
    indent = _key_indent(lines, start, end)
    for index in range(start + 1, end):
        match = KEY.match(lines[index])
        if match and _indent(lines[index]) == indent and match.group(2) == key:
            return index, _key_block_end(lines, index, indent)
    return None


def _put(lines: list[str], start: int, end: int, key: str, value: str,
         before: str = "") -> list[str]:
    """Set `key: value` on the item, appended last or ahead of `before`; sibling keys keep order."""
    span = _key_span(lines, start, end, key)
    rendered = f"{' ' * _key_indent(lines, start, end)}{key}: {value}"
    if span is not None:
        return [*lines[:span[0]], rendered, *lines[_content_end(lines, *span):]]
    at = _content_end(lines, start, end)
    anchor = _key_span(lines, start, end, before) if before else None
    at = anchor[0] if anchor else at
    return [*lines[:at], rendered, *lines[at:]]


def _column_lines(name: str, keys: dict, indent: int) -> list[str]:
    """A `columns[]` entry at `indent`, with its keys one level in."""
    pad = " " * indent
    return [f"{pad}- name: {name}",
            *(f"{pad}  {key}: {value}" for key, value in keys.items())]


def _first_item_indent(lines: list[str], lo: int, hi: int, default: int) -> int:
    for index in range(lo, hi):
        match = ITEM.match(lines[index])
        if match:
            return len(match.group(1))
    return default + 2


def _set_column(lines: list[str], start: int, end: int, column: str, key: str,
                value: str) -> list[str]:
    """Put `key: value` on a column entry, adding the entry when the model has none."""
    span = _key_span(lines, start, end, "columns")
    if span is None:
        at = _content_end(lines, start, end)
        indent = _key_indent(lines, start, end)
        return [*lines[:at], f"{' ' * indent}columns:",
                *_column_lines(column, {key: value}, indent + 2), *lines[at:]]
    index, columns_end = span
    item = _entry(lines, column, index + 1, columns_end)
    if item is not None:
        return _put(lines, item[0], item[1], key, value)
    at = _content_end(lines, index + 1, columns_end)
    indent = _first_item_indent(lines, index + 1, columns_end, _indent(lines[index]))
    return [*lines[:at], *_column_lines(column, {key: value}, indent), *lines[at:]]


def _entry_lines(table: str, owned: dict, indent: int) -> list[str]:
    """A whole properties entry, for a file that has none for this relation."""
    pad = " " * indent
    lines = [f"{pad}- name: {table}"]
    if "contract" in owned:
        lines.append(f"{pad}  contract: {_flow(owned['contract'])}")
    if owned["columns"]:
        lines.append(f"{pad}  columns:")
        for column, keys in owned["columns"].items():
            lines.extend(_column_lines(column, {k: _flow(v) for k, v in keys.items()},
                                       indent + 4))
    return lines


def _flow(value) -> str:
    """One line of YAML: a scalar, or a collection in flow style."""
    return yaml.safe_dump(value, default_flow_style=True, width=1000).removesuffix(
        "\n...\n").strip()


def _drop_renamed_tests(lines: list[str], start: int, end: int, column: str,
                        keys: dict) -> list[str]:
    """Drop a column's `tests` when `data_tests` now states exactly the same rules.

    dbt refuses both keys on one column, so writing the same list again is a rename rather than
    a second declaration. A list that differs is left alone: the refusal is then dbt's to make.
    The whole block is parsed, so a block sequence and a flow list compare as the rules they are.
    """
    if "data_tests" not in keys:
        return lines
    block = _key_span(lines, start, end, "columns")
    if block is None:
        return lines
    item = _entry(lines, column, block[0] + 1, block[1])
    if item is None:
        return lines
    span = _key_span(lines, item[0], item[1], "tests")
    if span is None:
        return lines
    block_end = _content_end(lines, *span)
    declared = yaml.safe_load("\n".join(lines[span[0]:block_end]))
    if not isinstance(declared, dict) or declared.get("tests") != keys["data_tests"]:
        return lines
    return [*lines[:span[0]], *lines[block_end:]]


def _apply(text: str, section: str, table: str, owned: dict) -> str:
    """The properties file with this relation's owned keys written in; everything else intact."""
    lines = text.splitlines()
    span = _section(lines, section)
    if span is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(f"{section}:")
        span = (len(lines), len(lines))
    found = _entry(lines, table, *span)
    if found is None:
        at = _content_end(lines, *span)
        lines[at:at] = _entry_lines(table, owned, _first_item_indent(lines, *span, 0))
        return _joined(lines)
    # Re-found after every insertion: the file is small and the line numbers move.
    start, end = found
    for column, keys in owned["columns"].items():
        for key, value in keys.items():
            lines = _set_column(lines, start, end, column, key, _flow(value))
            start, end = _entry(lines, table, *_section(lines, section))
        lines = _drop_renamed_tests(lines, start, end, column, keys)
        start, end = _entry(lines, table, *_section(lines, section))
    if "contract" in owned:
        lines = _put(lines, start, end, "contract", _flow(owned["contract"]), before="columns")
    return _joined(lines)


def _joined(lines: list[str]) -> str:
    return "\n".join(lines).rstrip("\n") + "\n"


def _base(path: Path) -> str:
    """A properties file's text; one to be created starts as a bare dbt properties document."""
    return path.read_text(encoding="utf-8") if path.is_file() else "version: 2\n"


def _module_text(tables: dict[str, dict[str, dict]]) -> str:
    """The dlt hints module, written deterministically so a re-run is byte-identical."""
    lines = [
        '"""dlt column hints, generated from the data contracts.',
        "",
        "Do not edit: `generate` owns this file and `check` fails when it is stale.",
        '"""',
        "",
        "COLUMNS: dict[str, dict[str, dict]] = {",
    ]
    for table in sorted(tables):
        lines.append(f'    "{table}": {{')
        for column, hint in tables[table].items():
            kind = hint["data_type"]
            nullable = hint["nullable"]
            lines.append(f'        "{column}": {{"data_type": "{kind}", '
                         f'"nullable": {nullable}}},')
        lines.append("    },")
    lines.append("}")
    return "\n".join(lines) + "\n"


def _columns_module(path: Path) -> dict | None:
    """The generated module's COLUMNS, read without importing it; None when it does not parse."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, ValueError):
        return None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            target = node.targets[0]
        elif isinstance(node, ast.AnnAssign):
            target = node.target
        else:
            continue
        if getattr(target, "id", "") == "COLUMNS" and node.value is not None:
            return ast.literal_eval(node.value)
    return {}


def _display(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _stale(path: Path, root: Path, key: str) -> dict:
    return _diag(
        "error", "generated/stale",
        f"{_display(path, root)}: {key} is stale; run generate. If the contract no longer "
        f"produces this key at all, remove the key instead — generate only writes the keys a "
        f"contract yields and never deletes one, so a withdrawn rule or a dropped property is "
        f"the one case it cannot clear",
    )


# The column keys `generate` owns per kind: what it writes, plus `tests`, the legacy spelling it
# renames to `data_tests`. A floor, not a lookup of what this contract happened to yield: a key
# `generate` writes for the kind is reportable even where this contract states no instance.
OWNED_COLUMN_KEYS = {"model": ("data_type", "data_tests", "tests"),
                     "seed": ("data_tests", "tests")}


def _stale_keys(found: dict, owned: dict, kind: str, table: str) -> list[str]:
    """Owned column keys on disk that `_owned` does not produce here.

    The vocabulary is the kind's capability set union `_owned`'s own output for this contract, so
    a key the contract does not state is still reportable: `generate` never deletes a key it
    cannot account for, and a leftover must be visible rather than disappear with the vocabulary.
    A legacy `tests` list is always a leftover, because `generate` renames every one it can
    restate to `data_tests`, and dbt refuses a column carrying both.
    """
    stale = [f"{table}.contract"] if "contract" in found and "contract" not in owned else []
    column_keys = sorted(
        set(OWNED_COLUMN_KEYS.get(kind, ()))
        | {key for keys in owned["columns"].values() for key in keys}
    )
    for column in found.get("columns") or []:
        if not isinstance(column, dict):
            continue
        declared = owned["columns"].get(column.get("name"), {})
        stale.extend(f"{table}.columns.{column.get('name')}.{key}"
                     for key in column_keys if key in column and key not in declared)
    return stale


def _stale_diagnostics(root: Path, repo_map: dict, contracts: dict,
                       docs: dict) -> list[dict]:
    """What `generate` would write, against what is on disk: one computation, no second copy.

    A contract whose generated artifact or entry is absent is stale: `generate` never having
    run is exactly the drift this check exists to catch.
    """
    targets: dict[Path, list[tuple[tuple[str, str], dict, str]]] = {}
    diags: list[dict] = []
    for relation, _ in sorted(contracts.items()):
        doc = docs.get(relation)
        if doc is None:
            continue
        try:
            target = _target(root, repo_map, relation)
        except _Refused as refusal:
            diags.append(refusal.diag)
            continue
        if target is not None:
            targets.setdefault(target[1], []).append((relation, doc, target[0]))

    hints: dict[str, dict[str, dict]] = {}
    module: Path | None = None
    on_disk_module: dict = {}
    for path, entries in sorted(targets.items()):
        if entries[0][2] == "dlt":
            module = path
            on_disk_module = _columns_module(path) if path.is_file() else {}
        else:
            doc = yaml.safe_load(path.read_text(encoding="utf-8")) if path.is_file() else {}
        for relation, contract, kind in entries:
            try:
                owned = _owned(relation, contract, kind)
            except _Refused as refusal:
                diags.append(refusal.diag)
                continue
            if kind == "dlt":
                hints[relation[1]] = owned["columns"]
                continue
            table, section = relation[1], PROPERTIES_SECTION[kind]
            found = _document_entry(doc, section, table)
            if found is None:
                diags.append(_stale(path, root, f"{section}.{table}"))
                continue
            if "contract" in owned and found.get("contract") != owned["contract"]:
                diags.append(_stale(path, root, f"{table}.contract"))
            for key in _stale_keys(found, owned, kind, table):
                diags.append(_stale(path, root, key))
            columns = {column.get("name"): column
                       for column in found.get("columns") or [] if isinstance(column, dict)}
            for column, keys in owned["columns"].items():
                for key, value in keys.items():
                    if (columns.get(column) or {}).get(key) != value:
                        diags.append(_stale(path, root, f"{table}.columns.{column}.{key}"))

    if hints and module is not None:
        if not module.is_file() or on_disk_module is None:
            diags.append(_stale(module, root, "COLUMNS"))
        else:
            for table in sorted(set(hints) | set(on_disk_module)):
                want, got = hints.get(table) or {}, on_disk_module.get(table) or {}
                for column in sorted(set(want) | set(got)):
                    if want.get(column) != got.get(column):
                        diags.append(_stale(module, root, f'COLUMNS["{table}"]["{column}"]'))
    return diags


# The `servers[].type` each platform kind maps to. A kind the standard names maps to itself; one
# it does not is `custom`, the type the standard keeps for a technology it has no type for.
SERVER_TYPES = {
    "duckdb_local": "duckdb",
    "motherduck": "duckdb",
    "bigquery": "bigquery",
    "databricks": "databricks",
    "redshift": "redshift",
    "snowflake": "snowflake",
    "fabric_lakehouse": "custom",
    "fabric_warehouse": "custom",
}


def _platform(repo_map: dict) -> str:
    """The platform the map declares. One Domain runs on one, so the map is the only source."""
    return str(repo_map.get("data_platform") or "")


def _catalog_path(root: Path) -> Path | None:
    """The warehouse `--relations` reads: the ephemeral path the platform sets, else the repo file."""
    declared = os.environ.get("VD_EPHM_DUCKDB_LOCAL_PATH")
    candidate = Path(declared) if declared else root / WAREHOUSE_FILE
    return candidate if candidate.is_file() else None


def _server_diagnostics(relation: tuple[str, str], path: Path, doc: dict,
                        repo_map: dict, root: Path) -> list[dict]:
    """A contract's `servers` against the platform the map declares."""
    expected = _server(root, repo_map, relation)
    if "servers" not in doc:
        # An empty list is the empty-section check's finding, not a second one here.
        return [_diag("error", "servers/mismatch",
                      f"{path}: no `servers`, and the map declares `{_platform(repo_map)}`; a "
                      f"contract states the platform that serves it")]
    for server in doc.get("servers") or []:
        if not isinstance(server, dict):
            continue
        wrong = [
            f"`{field}` is {server.get(field)!r} and the map's `{_platform(repo_map)}` platform "
            f"makes it {want!r}"
            for field in ("type", "database")
            if (want := expected.get(field)) is not None and server.get(field) != want
        ]
        want_platform = next(
            (p.get("value") for p in expected.get("customProperties") or []
             if p.get("property") == "platform"), None)
        if want_platform is not None:
            got_platform = next(
                (p.get("value") for p in server.get("customProperties") or []
                 if p.get("property") == "platform"), None)
            if got_platform != want_platform:
                wrong.append(
                    f"`customProperties.platform` is {got_platform!r} and the map's platform "
                    f"makes it {want_platform!r}")
        if wrong:
            return [_diag("error", "servers/mismatch", f"{path}: " + "; ".join(wrong))]
    return []


def _declared_name(relation: tuple[str, str], path: Path, doc: dict) -> list[dict]:
    """The contract's own `schema[].name` against the relation its path names.

    The path places the file; the name is what a consumer reads. A rename of one without the
    other leaves a contract describing a relation that does not exist.
    """
    names = [
        element.get("name")
        for element in doc.get("schema") or []
        if isinstance(element, dict) and element.get("name")
    ]
    if not names:
        return []
    if relation[1] in names:
        return []
    return [_diag("error", "contract/misnamed",
                  f"{path}: `schema[].name` is {names[0]!r} and the path names "
                  f"`{relation[1]}`; a contract states the relation it governs")]


def _relation_diagnostics(relation: tuple[str, str], path: Path, doc: dict,
                          catalog: Path, repo_map: dict) -> list[dict]:
    """The contract's columns against the columns the catalog holds for the relation.

    A column the catalog has and the contract does not is the drift this exists for: the
    contract states the shape, and the landed relation still carries a column it dropped.
    """
    con = duckdb.connect(str(catalog), read_only=True)
    try:
        rows = con.execute(
            "select column_name from information_schema.columns "
            "where table_schema = ? and table_name = ?",
            [relation[0], relation[1]],
        ).fetchall()
    finally:
        con.close()
    # A loader column is not the relation's shape, the same rule the contract side applies.
    landed = {row[0] for row in rows if not _is_loader_column(relation, row[0], repo_map)}
    if not rows:
        return [_diag("error", "relations/mismatch",
                      f"{relation[0]}.{relation[1]}: the catalog holds no such relation, so the "
                      f"contract describes nothing; build it before comparing")]
    declared = {
        prop.get("name")
        for element in doc.get("schema") or []
        if isinstance(element, dict)
        for prop in element.get("properties") or []
        if isinstance(prop, dict) and prop.get("name")
    }
    diags = []
    for name in sorted(declared - landed):
        diags.append(_diag("error", "relations/mismatch",
                           f"{relation[0]}.{relation[1]}: the contract declares `{name}` and the "
                           f"built relation has no such column"))
    for name in sorted(landed - declared):
        diags.append(_diag("error", "relations/mismatch",
                           f"{relation[0]}.{relation[1]}: the built relation carries `{name}` and "
                           f"the contract does not declare it"))
    return diags


def _server(root: Path, repo_map: dict, relation: tuple[str, str]) -> dict:
    """Where the relation lives: the Domain as the server, the platform as the type."""
    platform = _platform(repo_map)
    kind = SERVER_TYPES.get(platform, "custom")
    server = {
        "server": repo_map.get("repo_root") or root.name,
        "type": kind,
    }
    if platform == "duckdb_local":
        server["database"] = WAREHOUSE_FILE
    server["schema"] = relation[0]
    if kind == "custom":
        server["customProperties"] = [{"property": "platform", "value": platform or "unknown"}]
    return server


def _properties_entry(root: Path, repo_map: dict, relation: tuple[str, str]) -> dict | None:
    """The relation's entry in the dbt properties file that already names it, if one does.

    True of a dbt model and a seed; a dlt-loaded relation has no properties file, so it has
    nothing to contribute and nothing is looked for.
    """
    layer = _layer_for(repo_map, relation[0])
    if layer is None or layer.get("built_by") != "dbt" or not layer.get("path"):
        return None
    kind = "seed" if (root / layer["path"] / f"{relation[1]}.csv").is_file() else "model"
    path = _properties_file(root, layer, relation[1], PROPERTIES_SECTION[kind])
    if not path.is_file():
        return None
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (yaml.YAMLError, OSError):
        return None
    return _document_entry(doc, PROPERTIES_SECTION[kind], relation[1])


def _logical_types(relation: tuple[str, str], column: str, physical: str,
                   field: dict | None) -> tuple[str | None, bool]:
    """(logicalType, carries a timezone) for one column.

    The canonical model's `datatype` wins where it declares the field: it is the agreed
    meaning, and the contract exists to agree with it. The physical type answers otherwise.
    """
    datatype = (field or {}).get("datatype")
    if datatype in LOGICAL_TYPES:
        return LOGICAL_TYPES[datatype], datatype == "DateTimeTz"
    base = physical.split("(", 1)[0].strip().upper()
    logical = PHYSICAL_LOGICAL.get(base)
    if logical is None:
        raise _Refused(_diag("error", "contract/unmapped-type",
                             f"{relation[0]}.{relation[1]}.{column}: `{physical}` has no ODCS "
                             f"logicalType"))
    return logical, "WITH TIME ZONE" in base


def _declared_tests(column: dict | None):
    """The generic tests a dbt column entry declares, as (name, arguments) pairs."""
    declared = (column or {}).get("tests") or (column or {}).get("data_tests") or []
    for test in declared:
        if isinstance(test, str):
            yield test, {}
        elif isinstance(test, dict) and len(test) == 1:
            name, arguments = next(iter(test.items()))
            yield name, arguments if isinstance(arguments, dict) else {}


def _quality_rules(column: dict | None) -> list[dict]:
    """The rules an existing dbt generic test already asserts, in the shape `generate` reads."""
    rules = []
    for name, arguments in _declared_tests(column):
        if name not in RULE_METRICS:
            continue
        rule: dict = {"type": "library", "metric": RULE_METRICS[name]}
        if name == "accepted_values":
            values = arguments.get("values") or (arguments.get("arguments") or {}).get("values")
            if not values:
                continue
            rule["arguments"] = {"valid_values": list(values)}
        rule["mustBe"] = 0
        rules.append(rule)
    return rules


def _relationships(column: dict | None) -> list[dict]:
    """Every `relationships` test as the property-level foreign key it asserts."""
    found = []
    for name, arguments in _declared_tests(column):
        if name != "relationships":
            continue
        # dbt nests a generic test's parameters under `arguments`; the flat form predates it.
        arguments = arguments.get("arguments") or arguments
        field = arguments.get("field")
        target = str(arguments.get("to") or "")
        match = REF_REFERENCE.search(target) or SOURCE_REFERENCE.search(target)
        if match and field:
            found.append({"to": f"{match.group(1)}.{field}"})
    return found


def _catalog_relations(catalog: Path, repo_map: dict,
                       expected: dict[tuple[str, str], str]) -> dict[tuple[str, str], list[dict]]:
    """Every column of every relation a contract is owed for, in catalog order.

    A relation the map declares is owed one; so is a loader audit relation, which no declared
    resource builds. `_dlt_*` bookkeeping and a table nothing declares are not.
    """
    import duckdb

    try:
        con = duckdb.connect(str(catalog), read_only=True)
        try:
            rows = con.execute(
                """
                select table_schema, table_name, column_name, data_type, is_nullable
                from information_schema.columns
                where table_schema not in ('information_schema', 'pg_catalog')
                order by table_schema, table_name, ordinal_position
                """
            ).fetchall()
        finally:
            con.close()
    except duckdb.Error as exc:
        raise _Refused(_diag("error", "catalog/unreadable", f"{catalog}: {exc}"))

    relations: dict[tuple[str, str], list[dict]] = {}
    for schema, table, column, physical, nullable in rows:
        relation = (schema, table)
        if table.startswith("_dlt"):
            continue
        if relation not in expected and not _is_audit(relation, repo_map):
            continue
        if _is_loader_column(relation, column, repo_map):
            continue
        relations.setdefault(relation, []).append({
            "name": column, "physicalType": physical, "nullable": nullable != "NO",
        })
    return relations


def _identifier(name: str) -> str:
    """A column name as a quoted identifier, so a reserved word or a space still resolves."""
    return '"' + name.replace('"', '""') + '"'


def _relation_sql(relation: tuple[str, str]) -> str:
    return f"{_identifier(relation[0])}.{_identifier(relation[1])}"


def _relation_evidence(con, relation: tuple[str, str], columns: list[dict]) -> dict:
    """Rows, nulls and distinct values per column, from the warehouse itself.

    One aggregate per relation: a finding is a claim about the data, so the data is what
    settles it, and an aggregate is the same answer on every run.
    """
    select = ["count(*) as total"]
    for index, column in enumerate(columns):
        name = _identifier(column["name"])
        select.append(f"count(*) filter (where {name} is null) as nulls_{index}")
        select.append(f"count(distinct {name}) as distinct_{index}")
    row = con.execute(f"select {', '.join(select)} from {_relation_sql(relation)}").fetchone()
    evidence = {"rows": row[0], "columns": {}}
    for index, column in enumerate(columns):
        evidence["columns"][column["name"]] = {
            "nulls": row[1 + 2 * index], "distinct": row[2 + 2 * index],
        }
    return evidence


def _evidence(catalog: Path, relations: dict[tuple[str, str], list[dict]]) -> dict:
    """The data behind every relation a contract is owed for."""
    import duckdb

    evidence: dict[tuple[str, str], dict] = {}
    try:
        con = duckdb.connect(str(catalog), read_only=True)
        try:
            for relation, columns in sorted(relations.items()):
                evidence[relation] = _relation_evidence(con, relation, columns)
        finally:
            con.close()
    except duckdb.Error as exc:
        raise _Refused(_diag("error", "catalog/unreadable", f"{catalog}: {exc}"))
    return evidence


def _settled_metrics(prop: dict) -> set[str]:
    """The rules that assert zero violations: only those settle a doubt."""
    return {
        rule.get("metric")
        for rule in prop.get("quality") or []
        if isinstance(rule, dict) and rule.get("type") == "library" and rule.get("mustBe") == 0
    }


def _property_findings(relation: tuple[str, str], prop: dict, rows: int, statistics: dict,
                       keys: set[str]) -> list[dict]:
    """The doubts one contract property leaves open, each with the evidence gathered so far."""
    name = prop["name"]
    where = f"{relation[0]}.{relation[1]}.{name}"
    nulls, distinct = statistics["nulls"], statistics["distinct"]
    non_null = rows - nulls
    settled = _settled_metrics(prop)
    diags = []
    if not _prose(prop.get("description")):
        diags.append(_diag("warning", UNDESCRIBED,
                           f"{where}: no description; what does {name} mean?"))
    if nulls and not prop.get("required") and "nullValues" not in settled:
        diags.append(_diag("warning", UNPROVEN_NULLABLE,
                           f"{where}: {nulls} of {rows} rows are null and no rule settles whether "
                           f"that is allowed; is {name} required, or is a null a real state?"))
    repeats = rows > 0 and distinct < non_null
    candidate_key = name in keys or KEY_SHAPED.search(name) is not None
    if candidate_key and repeats:
        diags.append(_diag("warning", KEY_REPEATS,
                           f"{where}: {non_null - distinct} duplicate value(s) across {non_null} "
                           f"non-null rows under a key name; which column(s) identify one row of "
                           f"{relation[1]}, and is {name} one of them or a repeated reference — if "
                           f"a reference, what does it target?"))
    # An identifier's value set is not a domain: "which values are valid" has a false premise for
    # a key, whose own question (class 6) asks what it points at instead.
    if (rows and 1 < distinct <= ENUM_MAX_DISTINCT and distinct < rows
            and prop.get("logicalType") == "string" and "invalidValues" not in settled
            and REFERENCE_SHAPED.search(name) is None):
        diags.append(_diag("warning", OPEN_ENUM,
                           f"{where}: {distinct} distinct values and no accepted_values test; "
                           f"which values are valid, and is the set closed?"))
    if (REFERENCE_SHAPED.search(name) is not None and not name.startswith("_dlt")
            and not prop.get("relationships") and not prop.get("primaryKey")
            and not (candidate_key and repeats)):
        diags.append(_diag("warning", UNDECLARED_FOREIGN_KEY,
                           f"{where}: the name reads as a reference and no relationships test "
                           f"states its target; what does {name} reference, or is it this "
                           f"relation's own identifier?"))
    return diags


def _findings(relation: tuple[str, str], contract: dict, evidence: dict,
              keys: set[str]) -> list[dict]:
    """Every doubt one contract leaves open, as the question that would settle it.

    A finding is raised only where neither the contract, the canonical model, the dbt tests nor
    the data settle the point: what is already answered is not queued, and nothing is guessed.
    """
    label = f"{relation[0]}.{relation[1]}"
    elements = [element for element in contract.get("schema") or [] if isinstance(element, dict)]
    element = elements[0] if elements else {}
    description = contract.get("description")
    purpose = description.get("purpose") if isinstance(description, dict) else description
    diags = []
    if not _prose(element.get("dataGranularityDescription")):
        diags.append(_diag("warning", NO_GRAIN,
                           f"{label}: no grain statement; what does one row of "
                           f"{relation[1]} represent?"))
    if not any(_prose(prose) for prose in
               (purpose, element.get("description"), element.get("dataGranularityDescription"))):
        diags.append(_diag("warning", UNDESCRIBED,
                           f"{label}: nothing describes this table; what is {relation[1]} for?"))
    for name, prop in sorted(_properties(contract).items()):
        diags.extend(_property_findings(
            relation, prop, evidence["rows"],
            evidence["columns"].get(name) or {"nulls": 0, "distinct": 0}, keys))
    return diags


def _draft(root: Path, repo_map: dict, relation: tuple[str, str], columns: list[dict],
           documents: dict[tuple[str, str], tuple[dict, Path]]) -> dict:
    """One contract, holding only what the catalog, the canonical model and dbt already state."""
    schema, table = relation
    document = documents.get(relation)
    dataset = document[0] if document else {}
    entry = _properties_entry(root, repo_map, relation) or {}
    fields = {field["name"]: field for field in dataset.get("fields") or []
              if isinstance(field, dict) and field.get("name")}
    described = {column["name"]: column for column in entry.get("columns") or []
                 if isinstance(column, dict) and column.get("name")}
    keys = set(dataset.get("primary_key") or [])

    element: dict = {"name": table}
    grain = _prose(dataset.get("description")) or _prose(entry.get("description"))
    if grain:
        element["dataGranularityDescription"] = grain

    properties = []
    for column in columns:
        field = fields.get(column["name"])
        declared = described.get(column["name"])
        logical, timezone = _logical_types(relation, column["name"], column["physicalType"], field)
        prop: dict = {"name": column["name"]}
        if logical:
            prop["logicalType"] = logical
        prop["physicalType"] = column["physicalType"]
        if timezone:
            prop["logicalTypeOptions"] = {"timezone": True}
        if not column["nullable"]:
            prop["required"] = True
        if column["name"] in keys:
            prop["primaryKey"] = True
        description = (_prose((declared or {}).get("description"))
                       or _prose((field or {}).get("description")))
        if description:
            prop["description"] = description
        rules = _quality_rules(declared)
        if rules:
            prop["quality"] = rules
        relationships = _relationships(declared)
        if relationships:
            prop["relationships"] = relationships
        properties.append(prop)
    if properties:
        element["properties"] = properties

    doc = {
        "apiVersion": SPEC_VERSION,
        "kind": "DataContract",
        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{schema}.{table}")),
        "name": table,
        "version": "1.0.0",
        "status": "active",
        "servers": [_server(root, repo_map, relation)],
        "schema": [element],
    }
    if _is_audit(relation, repo_map):
        doc["description"] = {"purpose": AUDIT_PURPOSE}
    if document is not None:
        doc["authoritativeDefinitions"] = [
            {"url": _display(document[1], root), "type": "businessDefinition"},
        ]
    return doc


def _reviewed(target: Path, draft: dict, existing: bool) -> dict:
    """The contract a reader would find: the committed one, unless it cannot be read.

    `reverse` leaves a reviewed file alone, so the findings triage what is on disk rather than
    the draft it would have written. A file that does not parse contributes the draft; `check`
    is where a broken contract fails.
    """
    if not existing:
        return draft
    try:
        doc = yaml.safe_load(target.read_text(encoding="utf-8"))
    except (yaml.YAMLError, OSError):
        return draft
    return doc if isinstance(doc, dict) else draft


def _dump(doc: dict) -> str:
    """One contract as YAML: the order it was built in, never wrapped, so a re-run is identical.

    The dumper indents a block sequence under its key, which is how the rest of the repo's
    YAML reads; PyYAML's default puts it flush with the key.
    """
    return yaml.dump(doc, Dumper=_IndentedDumper, sort_keys=False, allow_unicode=True, width=1000)


@app.command()
def version():
    """Pin report: tool, standard version and the vendored upstream commit, as JSON."""
    # Also forces Typer group mode so `check` keeps its subcommand name once
    # `reverse` and `generate` land beside it.
    print(json.dumps({"tool": "odcs", "spec": SPEC_VERSION, "upstream_commit": UPSTREAM_COMMIT}))


@app.command()
def reverse(root: str = "", catalog: str = "", force: bool = False):
    """Draft one contract per relation, grounded only in the catalog, the model and dbt.

    The warehouse is the physical truth: every property and its type comes from
    `information_schema`. A field the canonical model declares overrides the physical type, and
    an existing dbt generic test becomes a quality rule or a declared relationship. Nothing is
    invented: a relation no description reaches, or a gold relation no document names, is left
    for the review rather than filled in. The id is derived from the relation, so a forced
    rewrite reproduces every file.

    An existing contract is a draft the review already worked on, so this leaves it alone and
    reports how many it skipped; `--force` rewrites them all.

    Every relation also yields its open questions as `finding/*` warnings, computed against the
    contract on disk (or the draft, where there is none): a doubt the model, the tests or the
    data already settles is not raised, and one nothing settles is, naming the relation, the
    column and the question that would close it.
    """
    repo_root = Path(root).resolve() if root else _repo_root(APP_DIR)
    repo_map = _repo_map(repo_root)
    raw = (repo_map.get("artifact_paths") or {}).get("data_contract")
    try:
        if not raw:
            raise _Refused(_diag("error", "contract/unconfigured",
                                 "repo-map.json declares no artifact_paths.data_contract, so no "
                                 "contract can be placed"))
        warehouse = Path(catalog).resolve() if catalog else repo_root / WAREHOUSE_FILE
        if not warehouse.is_file():
            raise _Refused(_diag("error", "catalog/missing",
                                 f"{warehouse}: no DuckDB warehouse to read; build the Domain or "
                                 f"pass --catalog"))
        documents = _canonical_datasets(repo_root, repo_map)
        relations = _catalog_relations(
            warehouse, repo_map, expected_relations(repo_root, repo_map))
        evidence = _evidence(warehouse, relations)
    except _Refused as refusal:
        print(json.dumps([refusal.diag]))
        raise typer.Exit(1)

    drafts: list[tuple[tuple[str, str], dict]] = []
    diags: list[dict] = []
    for relation, columns in sorted(relations.items()):
        try:
            drafts.append((relation, _draft(repo_root, repo_map, relation, columns, documents)))
        except _Refused as refusal:
            diags.append(refusal.diag)
    if diags:
        print(json.dumps(diags))
        raise typer.Exit(1)

    base = _declared(repo_root, raw)
    keys = {
        relation: set(dataset.get("primary_key") or [])
        for relation, (dataset, _) in documents.items()
    }
    findings: list[dict] = []
    skipped = 0
    for relation, doc in drafts:
        target = base / relation[0] / f"{relation[1]}.odcs.yaml"
        existing = target.is_file() and not force
        if existing:
            skipped += 1
        findings.extend(_findings(
            relation, _reviewed(target, doc, existing), evidence[relation],
            keys.get(relation, set())))
        if existing:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_dump(doc), encoding="utf-8")
    findings.sort(key=lambda diag: (diag["message"].split(": ", 1)[0], diag["code"]))
    if skipped:
        findings.append(_diag(
            "warning", "contract/exists",
            f"{skipped} contract(s) already exist and were left alone; pass --force to rewrite "
            f"them"))
    print(json.dumps(findings))


@app.command()
def generate(root: str = ""):
    """Write the dbt contract keys and dlt column hints that the contracts own.

    Only the keys this tool owns are written, and nothing is written at all when a contract
    already disagrees with the map: a contract set that is inconsistent is not a source.
    """
    repo_root = Path(root).resolve() if root else _repo_root(APP_DIR)
    repo_map = _repo_map(repo_root)
    try:
        contracts = _committed_contracts(repo_root, repo_map)
    except _Refused as refusal:
        print(json.dumps([refusal.diag]))
        raise typer.Exit(1)

    texts: dict[Path, str] = {}
    hints: dict[str, dict[str, dict]] = {}
    diags: list[dict] = []
    for relation, path in sorted(contracts.items()):
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not isinstance(doc, dict):
                raise _Refused(_diag("error", "schema/invalid", f"{path}: not a mapping"))
            target = _target(repo_root, repo_map, relation)
            if target is None:
                continue
            kind, file = target
            owned = _owned(relation, doc, kind)
        except _Refused as refusal:
            diags.append(refusal.diag)
            continue
        except yaml.YAMLError as exc:
            diags.append(_diag("error", "schema/invalid", f"{path}: {exc}"))
            continue
        if kind == "dlt":
            hints[relation[1]] = owned["columns"]
        else:
            texts[file] = _apply(texts.get(file) or _base(file), PROPERTIES_SECTION[kind],
                                 relation[1], owned)

    if diags:
        print(json.dumps(diags))
        raise typer.Exit(1)

    for file, text in texts.items():
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text, encoding="utf-8")
    if hints:
        module = _hints_module(repo_root, repo_map)
        module.parent.mkdir(parents=True, exist_ok=True)
        module.write_text(_module_text(hints), encoding="utf-8")
    print(json.dumps([]))


@app.command()
def check(root: str = "", relations: bool = False):
    """Validate every committed contract against the repo map and the vendored schema.

    Where the repo has adopted a canonical model, a gold contract must also agree with the
    document that names its relation. A schema that model documents no relation in is not yet
    modelled: its gold relations warn (`contract/no-document`) instead of failing, because the
    review asks for those documents and the gate has nothing to agree with. A map that declares
    no gold layers leaves nothing to agree with at all: `map/no-gold-layers` reports that gap
    rather than inventing a set. `--relations` adds
    the comparison against the built relation and fails when no catalog resolves, rather than
    skipping: asking for the check and getting silence is the false pass it exists to prevent.
    """
    repo_root = Path(root).resolve() if root else _repo_root(APP_DIR)
    repo_map = _repo_map(repo_root)

    try:
        contracts = _committed_contracts(repo_root, repo_map)
    except _Refused as refusal:
        print(json.dumps([refusal.diag]))
        raise typer.Exit(1)

    expected = expected_relations(repo_root, repo_map)
    documents = _canonical_datasets(repo_root, repo_map)
    gold = _gold_schemas(repo_map, expected) if documents else set()
    # A schema the canonical model documents no relation in is not yet modelled: the review
    # asks for a document, the gate does not fail a relation that never had one to agree with.
    modelled = gold & {schema for schema, _ in documents}
    diags: list[dict] = []
    parsed: dict[tuple[str, str], dict] = {}

    # A canonical model with no gold layers declared leaves agreement unchecked. Saying so is the
    # report; guessing which layers are gold would gate relations the map never claimed.
    if documents and not (repo_map.get("gold_layers") or []):
        diags.append(_diag("warning", "map/no-gold-layers",
                           "repo-map.json declares no gold_layers, so no relation is gated against "
                           "the canonical model; declare the layers that hold gold"))

    for relation, declarer in sorted(expected.items()):
        if relation not in contracts:
            diags.append(_diag("error", "contract/missing",
                               f"{relation[0]}.{relation[1]}: declared by {declarer} and has no contract"))
    for relation, path in sorted(contracts.items()):
        if relation in expected or _is_audit(relation, repo_map):
            continue
        diags.append(_diag("error", "contract/orphan",
                           f"{path}: names no relation the map declares"))
    for relation, _path in sorted(contracts.items()):
        if relation[0] in gold and relation not in documents:
            diags.append(_diag("warning", "contract/no-document",
                               f"{relation[0]}.{relation[1]}: no canonical document names this "
                               f"gold relation; the review asks for one"))

    for relation, path in sorted(contracts.items()):
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            diags.append(_diag("error", "schema/invalid", f"{path}: {exc}"))
            continue
        if not isinstance(doc, dict):
            diags.append(_diag("error", "schema/invalid", f"{path}: not a mapping"))
            continue
        parsed[relation] = doc
        diags.extend(_schema_diagnostics(doc, path))
        diags.extend(_empty_sections(doc, path))
        diags.extend(_grain(doc, path))
        diags.extend(_declared_name(relation, path, doc))
        diags.extend(_loader_columns(relation, doc, repo_map))
        if documents:
            diags.extend(_gold_agreement(relation, path, doc, documents, modelled))

    diags.extend(_stale_diagnostics(repo_root, repo_map, contracts, parsed))

    for relation, path in sorted(contracts.items()):
        doc = parsed.get(relation)
        if doc is not None:
            diags.extend(_server_diagnostics(relation, path, doc, repo_map, repo_root))

    if relations:
        catalog = _catalog_path(repo_root)
        if catalog is None:
            diags.append(_diag(
                "error", "relations/no-catalog",
                "check --relations needs a built relation: set VD_EPHM_DUCKDB_LOCAL_PATH or "
                "build the warehouse the map declares",
            ))
        else:
            for relation, path in sorted(contracts.items()):
                doc = parsed.get(relation)
                if doc is not None:
                    diags.extend(_relation_diagnostics(relation, path, doc, catalog, repo_map))

    print(json.dumps(diags))
    raise typer.Exit(1 if any(d["severity"] == "error" for d in diags) else 0)


if __name__ == "__main__":
    app()

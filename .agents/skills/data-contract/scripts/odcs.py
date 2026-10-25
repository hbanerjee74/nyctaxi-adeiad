"""ODCS data-contract tooling for this repo.

Commands: `check` (schema and structure of the committed contracts, and their agreement
with the canonical model that names each gold relation), `check --relations` (adds the
comparison against the built relation), `reverse` (draft contracts from an existing
warehouse), `generate` (write the dbt keys and dlt hints from the contracts).

This script proves shape and reports facts. It never judges meaning: the grain, whether a
`required` is honest, and whether a quality rule encodes the real business answer are the
`validating-data-contract` review, not a pass/fail here.

Every location resolves from `repo-map.json`: a layer's `path` for the dbt models it builds,
the seeds layer for its CSVs, and a source's `docs` file for the resources it lands. The
warehouse is consulted only by `--relations`.

Usage:
  python3 scripts/odcs.py check [--root PATH] [--relations]
  python3 scripts/odcs.py generate [--root PATH]

JSON diagnostics go to stdout (agent-parseable); human prose to stderr.
Exit 0 when no errors (warnings allowed), 1 otherwise.
"""

import json
import ast
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

# Gold is every dbt layer that is neither staging, intermediate nor a seed. Raw layers are
# excluded by `built_by`, and this list is the one place the three names appear.
NON_GOLD_LAYERS = ("staging", "intermediate", "seeds")

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


def _grain(doc: dict, path: Path) -> list[dict]:
    """A warning, not an error: an onboarding run may leave the grain to review."""
    elements = [e for e in (doc.get("schema") or []) if isinstance(e, dict)]
    stated = [e for e in elements if str(e.get("dataGranularityDescription") or "").strip()]
    if stated:
        return []
    return [_diag("warning", "contract/no-grain",
                  f"{path}: no `dataGranularityDescription`; the review refuses a contract "
                  f"a shipped intent presents as complete without one")]


def _canonical_datasets(root: Path, repo_map: dict) -> dict[tuple[str, str], dict]:
    """Every dataset the canonical model declares, keyed by the relation its `source` names.

    Empty when the repo has adopted no canonical model: a contract set is not broken for
    lacking something it never promised to agree with.
    """
    raw = (repo_map.get("artifact_paths") or {}).get("logical_model")
    if not raw:
        return {}
    base = _declared(root, raw)
    datasets: dict[tuple[str, str], dict] = {}
    if not base.is_dir():
        return datasets
    for path in sorted(base.glob("*.ossie.yaml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for dataset in doc.get("datasets") or []:
            if not isinstance(dataset, dict):
                continue
            source = str(dataset.get("source") or "").split(".", 1)
            if len(source) == 2:
                datasets[(source[0], source[1])] = dataset
    return datasets


def _gold_schemas(repo_map: dict, expected: dict[tuple[str, str], str]) -> set[str]:
    """Schemas holding gold relations: a dbt layer the map builds, past raw and staging."""
    built = {schema for schema, _ in expected}
    return {
        layer["schema"]
        for name, layer in (repo_map.get("layers") or {}).items()
        if name not in NON_GOLD_LAYERS
        and layer.get("built_by") == "dbt"
        and layer.get("schema") in built
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


def _gold_agreement(relation: tuple[str, str], path: Path, contract: dict,
                    documents: dict[tuple[str, str], dict], gold: set[str]) -> list[dict]:
    """A gold contract against the canonical document that names its relation."""
    label = f"{relation[0]}.{relation[1]}"
    dataset = documents.get(relation)
    if dataset is None:
        if relation[0] not in gold:
            return []
        return [_diag("error", "gold/undeclared",
                      f"{path}: no canonical document names the gold relation {label}")]
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
    return diags


def _layer_for(repo_map: dict, schema: str) -> dict | None:
    """The layer that declares a schema; the map is the only place a schema is named."""
    for layer in (repo_map.get("layers") or {}).values():
        if layer.get("schema") == schema:
            return layer
    return None


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


def _data_tests(prop: dict) -> list:
    """The generic dbt tests the contract's quality rules reduce to."""
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
    return tests


def _owned(relation: tuple[str, str], contract: dict, kind: str) -> dict:
    """The keys `generate` owns for one contract, and nothing else.

    A model carries the enforced contract and a `data_type` per property; a seed carries only
    the generated tests, since dbt's contract is model-only; a dlt table carries its hints.
    A key the contract cannot ground is a refusal, never a guess.
    """
    for server in contract.get("servers") or []:
        stated = (server or {}).get("schema") if isinstance(server, dict) else None
        if stated and stated != relation[0]:
            raise _Refused(_diag("error", "contract/servers-mismatch",
                                 f"{relation[0]}.{relation[1]}: `servers[].schema` says "
                                 f"{stated!r}, the map declares {relation[0]!r}"))
    owned: dict = {"columns": {}}
    if kind == "model":
        owned["contract"] = {"enforced": True}
    for name, prop in _properties(contract).items():
        where = f"{relation[0]}.{relation[1]}.{name}"
        keys: dict = {}
        if kind == "seed":
            tests = _data_tests(prop)
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
        owned["columns"][name] = keys
    return owned


ITEM = re.compile(r"^(\s*)- name:\s*(.+?)\s*$")
KEY = re.compile(r"^(\s*)([A-Za-z_][\w-]*):\s*(.*)$")


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _block_end(lines: list[str], index: int, indent: int) -> int:
    """The line after the block that the `key:` or `- name:` line at `indent` opens."""
    for other in range(index + 1, len(lines)):
        text = lines[other].strip()
        if text and not text.startswith("#") and _indent(lines[other]) <= indent:
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
            return index + 1, _block_end(lines, index, 0)
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
            return index, _block_end(lines, index, indent)
    return None


def _put(lines: list[str], start: int, end: int, key: str, value: str,
         before: str = "") -> list[str]:
    """Set `key: value` on the item, appended last or ahead of `before`; sibling keys keep order."""
    span = _key_span(lines, start, end, key)
    rendered = f"{' ' * _key_indent(lines, start, end)}{key}: {value}"
    if span is not None:
        return [*lines[:span[0]], rendered, *lines[span[1]:]]
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
    return yaml.safe_dump(value, default_flow_style=True).removesuffix("\n...\n").strip()


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


def _columns_module(path: Path) -> dict:
    """The generated module's COLUMNS, read without importing it."""
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
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
    return _diag("error", "generated/stale",
                 f"{_display(path, root)}: {key} is stale; run generate")


def _stale_diagnostics(root: Path, repo_map: dict, contracts: dict,
                       docs: dict) -> list[dict]:
    """What `generate` would write, against what is on disk: one computation, no second copy.

    A target file that does not exist is not stale: nothing there claims to be generated.
    Every file that does exist must agree with the contracts it serves.
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
        if target is None or not target[1].is_file():
            continue
        targets.setdefault(target[1], []).append((relation, doc, target[0]))

    hints: dict[str, dict[str, dict]] = {}
    module: Path | None = None
    on_disk_module: dict = {}
    for path, entries in sorted(targets.items()):
        if entries[0][2] == "dlt":
            module, on_disk_module = path, _columns_module(path)
        else:
            doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
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
            columns = {column.get("name"): column
                       for column in found.get("columns") or [] if isinstance(column, dict)}
            for column, keys in owned["columns"].items():
                for key, value in keys.items():
                    if (columns.get(column) or {}).get(key) != value:
                        diags.append(_stale(path, root, f"{table}.columns.{column}.{key}"))

    if hints and module is not None:
        for table in sorted(set(hints) | set(on_disk_module)):
            want, got = hints.get(table) or {}, on_disk_module.get(table) or {}
            for column in sorted(set(want) | set(got)):
                if want.get(column) != got.get(column):
                    diags.append(_stale(module, root, f'COLUMNS["{table}"]["{column}"]'))
    return diags


@app.command()
def version():
    """Pin report: tool, standard version and the vendored upstream commit, as JSON."""
    # Also forces Typer group mode so `check` keeps its subcommand name once
    # `reverse` and `generate` land beside it.
    print(json.dumps({"tool": "odcs", "spec": SPEC_VERSION, "upstream_commit": UPSTREAM_COMMIT}))


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
    document that names its relation. `--relations` adds the comparison against the built
    relation and fails when no catalog resolves, rather than skipping: asking for the check
    and getting silence is the false pass it exists to prevent.
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
    diags: list[dict] = []
    parsed: dict[tuple[str, str], dict] = {}

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
        parsed[relation] = doc
        diags.extend(_schema_diagnostics(doc, path))
        diags.extend(_empty_sections(doc, path))
        diags.extend(_grain(doc, path))
        if documents:
            diags.extend(_gold_agreement(relation, path, doc, documents, gold))

    diags.extend(_stale_diagnostics(repo_root, repo_map, contracts, parsed))

    if relations:
        diags.append(_diag("error", "relations/not-implemented",
                           "check --relations is not implemented yet"))

    print(json.dumps(diags))
    raise typer.Exit(1 if any(d["severity"] == "error" for d in diags) else 0)


if __name__ == "__main__":
    app()

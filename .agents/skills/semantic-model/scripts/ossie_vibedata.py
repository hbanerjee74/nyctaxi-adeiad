"""VIBEDATA second-pass checks over an Ossie model document.

Runs after the vendored upstream `validate_document()`. Reads the
`VIBEDATA` entries in `custom_extensions` at model, dataset, and
relationship level and enforces the frozen key set plus OBIEE-style
LTS coverage: a field no LTS supplies is a broken model, and a mapping
that names an undeclared field fails rather than guessing.

Pure functions: input is the parsed YAML dict, output is a list of
`{"severity": ..., "code": ..., "message": ...}` diagnostics.
"""

import json

VENDOR = "VIBEDATA"

CARDINALITIES = {"many-to-one", "one-to-one", "many-to-many"}

MODEL_KEYS = {"vibedata_version", "physical_tables", "physical_joins"}
DATASET_KEYS = {"vibedata_version", "alias_of", "physical", "partitioned_by",
                "scd", "logical_sources", "hierarchies"}
RELATIONSHIP_KEYS = {"vibedata_version", "physical_join", "cardinality",
                     "join_type", "join_cost", "join_expression"}
PHYSICAL_TABLE_KEYS = {"name", "source", "dbt_model", "table_type", "alias_of", "role", "note"}
PHYSICAL_JOIN_KEYS = {"name", "from", "to"}
LTS_KEYS = {"name", "physical_table", "priority_group", "content_grain",
            "where", "note", "column_map"}
HIERARCHY_KEYS = {"name", "levels"}
SCD_KEYS = {"type", "natural_key", "valid_from", "valid_to", "is_current",
            "open_ended_value"}


def _unknown_keys(payload, allowed, where):
    return [{"severity": "error", "code": "vibedata/unknown-key",
             "message": f"{where}: unknown VIBEDATA key '{k}'"}
            for k in payload if k not in allowed]


def _extensions(node):
    """The decoded VIBEDATA payloads on a model/dataset/relationship node."""
    out = []
    if not isinstance(node, dict):
        return out
    for ext in node.get("custom_extensions") or []:
        if isinstance(ext, dict) and ext.get("vendor_name") == VENDOR:
            out.append(ext.get("data"))
    return out


def _collect_versions(doc):
    """Every vibedata_version in the document, with where it sits."""
    found = []

    def grab(node, where):
        if not isinstance(node, dict):
            return
        for data in _extensions(node):
            try:
                payload = json.loads(data)
            except (TypeError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict):
                found.append((payload.get("vibedata_version"), where))

    grab(doc, "model")
    for dataset in doc.get("datasets", []):
        grab(dataset, f"dataset '{dataset.get('name', '<unnamed>')}'")
    for rel in doc.get("relationships", []):
        grab(rel, f"relationship '{rel.get('name', '<unnamed>')}'")
    return found


def _decode(data, where):
    try:
        payload = json.loads(data)
    except (TypeError, json.JSONDecodeError) as e:
        return None, [{"severity": "error", "code": "vibedata/data-not-json",
                       "message": f"{where}: VIBEDATA data is not valid JSON: {e}"}]
    if not isinstance(payload, dict):
        return None, [{"severity": "error", "code": "vibedata/data-not-object",
                       "message": f"{where}: VIBEDATA data must be a JSON object"}]
    return payload, []


def _model_payload(model):
    """Model-level VIBEDATA payload. Duplicates are an error, not a merge."""
    diags = []
    raws = _extensions(model)
    if len(raws) > 1:
        diags.append({"severity": "error", "code": "vibedata/duplicate-entry",
                      "message": "model: multiple VIBEDATA entries; keep exactly one"})
    merged = {}
    for data in raws:
        payload, errs = _decode(data, "model")
        diags.extend(errs)
        if payload:
            merged.update(payload)
    return merged, diags


def physical_table_index(doc):
    """Model-level physical tables by name: identity fields used for drift checks."""
    payload, _ = _model_payload(doc)
    out = {}
    for t in payload.get("physical_tables", []):
        if isinstance(t, dict) and t.get("name"):
            out[t["name"]] = {k: t.get(k) for k in ("source", "dbt_model", "table_type", "alias_of", "role")}
    return out


def validate_vibedata(doc):
    """Second-pass VIBEDATA checks. Returns diagnostics (errors and warnings)."""
    diags = []
    if not isinstance(doc, dict) or "datasets" not in doc:
        return diags
    model_name = doc.get("name", "<unnamed>")

    versions = _collect_versions(doc)
    if any(v is None for v, _ in versions):
        diags.append({"severity": "error", "code": "vibedata/version-missing",
                      "message": f"model '{model_name}': every VIBEDATA payload carries "
                                 "vibedata_version"})
    elif len({v for v, _ in versions}) > 1:
        detail = ", ".join(f"{w}={v!r}" for v, w in versions)
        diags.append({"severity": "error", "code": "vibedata/version-mismatch",
                      "message": f"model '{model_name}': mixed vibedata_version: {detail}"})

    model_payload, errs = _model_payload(doc)
    diags.extend(errs)
    diags.extend(_unknown_keys(model_payload, MODEL_KEYS, "model"))
    physical_tables = {t.get("name"): t for t in model_payload.get("physical_tables", [])
                       if isinstance(t, dict) and t.get("name")}
    for t in model_payload.get("physical_tables", []):
        if not isinstance(t, dict) or not t.get("name"):
            diags.append({"severity": "error", "code": "vibedata/physical-table-nameless",
                          "message": f"model '{model_name}': physical_tables entry without a name"})
            continue
        diags.extend(_unknown_keys(t, PHYSICAL_TABLE_KEYS,
                                   f"physical table '{t['name']}'"))
        alias_of = t.get("alias_of")
        if alias_of and (alias_of not in physical_tables or alias_of == t["name"]):
            diags.append({"severity": "error", "code": "vibedata/alias-dangling",
                          "message": f"model '{model_name}': physical table '{t['name']}' "
                                     f"is an alias of unknown table '{alias_of}'"})
    joined = set()
    physical_join_names = set()
    for j in model_payload.get("physical_joins", []):
        if isinstance(j, dict):
            joined.add(j.get("from"))
            joined.add(j.get("to"))
    for name in sorted(physical_tables):
        if name not in joined:
            diags.append({"severity": "warning", "code": "vibedata/table-unjoined",
                          "message": f"model '{model_name}': physical table '{name}' appears "
                                     "in no physical join"})
    for j in model_payload.get("physical_joins", []):
        if not isinstance(j, dict):
            diags.append({"severity": "error", "code": "vibedata/join-not-object",
                          "message": f"model '{model_name}': physical join entry must be an object"})
            continue
        diags.extend(_unknown_keys(j, PHYSICAL_JOIN_KEYS,
                                   f"physical join '{j.get('name', '<unnamed>')}'"))
        physical_join_names.add(j.get("name"))
        for end in ("from", "to"):
            if j.get(end) not in physical_tables:
                diags.append({"severity": "error", "code": "vibedata/join-dangling",
                              "message": f"model '{model_name}': physical join "
                                         f"'{j.get('name', '<unnamed>')}' references unknown "
                                         f"physical table '{j.get(end)}'"})

    dataset_names = {d.get("name") for d in doc.get("datasets", []) if d.get("name")}
    metric_names = {m.get("name") for m in doc.get("metrics", []) if isinstance(m, dict) and m.get("name")}
    for dataset in doc.get("datasets", []):
        diags.extend(_validate_dataset(dataset, model_name, physical_tables, metric_names))
    for rel in doc.get("relationships", []):
        diags.extend(_validate_relationship(rel, model_name, dataset_names, physical_join_names))
        diags.extend(_validate_from_columns(rel, model_name, doc))
    return diags


def _validate_from_columns(rel, model_name, doc):
    """A relationship's from_columns must name fields the from dataset declares."""
    diags = []
    rel_name = rel.get("name", "<unnamed>")
    datasets = {d.get("name"): d for d in doc.get("datasets", []) if isinstance(d, dict)}
    source = datasets.get(rel.get("from"))
    columns = rel.get("from_columns")
    if not source or not isinstance(columns, list):
        return diags
    fields = {f.get("name") for f in source.get("fields", []) if isinstance(f, dict)}
    for column in columns:
        if column not in fields:
            diags.append({"severity": "error", "code": "relationship/from-column-unknown",
                          "message": f"relationship '{rel_name}' in model '{model_name}': "
                                     f"from_column '{column}' is not a declared field of "
                                     f"dataset '{rel.get('from')}'"})
    return diags


def _validate_dataset(dataset, model_name, physical_tables, metric_names):
    diags = []
    ds_name = dataset.get("name", "<unnamed>")
    where = f"dataset '{ds_name}'"
    fields = {f.get("name") for f in dataset.get("fields", []) if f.get("name")}
    suppliable = fields | metric_names
    payloads = []
    for data in _extensions(dataset):
        payload, errs = _decode(data, where)
        diags.extend(errs)
        if payload:
            payloads.append(payload)
    if len(payloads) > 1:
        diags.append({"severity": "error", "code": "vibedata/duplicate-entry",
                      "message": f"{where}: multiple VIBEDATA entries; keep exactly one"})
    if not payloads:
        diags.append({"severity": "warning", "code": "vibedata/no-payload",
                      "message": f"{where}: no VIBEDATA entry; logical sources, "
                                 "hierarchies, and SCD are unchecked"})
        return diags
    payload = {}
    for p in payloads:
        payload.update(p)
    diags.extend(_unknown_keys(payload, DATASET_KEYS, where))

    alias_of = payload.get("alias_of")
    if alias_of and alias_of not in physical_tables:
        diags.append({"severity": "error", "code": "vibedata/alias-dangling",
                      "message": f"{where}: alias_of unknown physical table '{alias_of}'"})

    for hier in payload.get("hierarchies", []):
        if not isinstance(hier, dict):
            diags.append({"severity": "error", "code": "vibedata/hierarchy-not-object",
                          "message": f"{where}: hierarchy entry must be an object"})
            continue
        diags.extend(_unknown_keys(hier, HIERARCHY_KEYS,
                                   f"{where} hierarchy '{hier.get('name', '<unnamed>')}'"))
        for level in hier.get("levels", []) or []:
            if level not in fields:
                diags.append({"severity": "error", "code": "vibedata/hierarchy-unknown-field",
                              "message": f"{where}: hierarchy '{hier.get('name', '<unnamed>')}' "
                                         f"level '{level}' is not a declared field"})

    scd = payload.get("scd")
    if scd:
        if not isinstance(scd, dict):
            diags.append({"severity": "error", "code": "vibedata/scd-not-object",
                          "message": f"{where}: scd must be an object"})
            scd = {}
        diags.extend(_unknown_keys(scd, SCD_KEYS, f"{where} scd"))
        if scd.get("type") not in (1, 2, 3):
            diags.append({"severity": "error", "code": "vibedata/scd-bad-type",
                          "message": f"{where}: scd.type must be 1, 2, or 3"})
        for key in ("natural_key", "valid_from", "valid_to", "is_current"):
            col = scd.get(key)
            if col and col not in fields:
                diags.append({"severity": "error", "code": "vibedata/scd-unknown-field",
                              "message": f"{where}: scd.{key} '{col}' is not a declared field"})

    partitioned_by = payload.get("partitioned_by")
    if partitioned_by is not None and (
            not isinstance(partitioned_by, list)
            or not all(isinstance(c, str) for c in partitioned_by)):
        diags.append({"severity": "error", "code": "vibedata/bad-partitioned-by",
                      "message": f"{where}: partitioned_by must be a list of column names"})

    sources = payload.get("logical_sources", [])
    if not isinstance(sources, list):
        diags.append({"severity": "error", "code": "vibedata/lts-not-list",
                      "message": f"{where}: logical_sources must be a list"})
        sources = []
    mapped_fields = set()
    detail_present = False
    field_suppliers = {}
    for src in sources:
        src_name = src.get("name", "<unnamed>") if isinstance(src, dict) else "<unnamed>"
        if not isinstance(src, dict):
            diags.append({"severity": "error", "code": "vibedata/lts-not-object",
                          "message": f"{where}: logical source '{src_name}' must be an object"})
            continue
        diags.extend(_unknown_keys(src, LTS_KEYS, f"{where} logical source '{src_name}'"))
        priority = src.get("priority_group", 1)
        if not isinstance(priority, int) or isinstance(priority, bool) or priority < 0:
            diags.append({"severity": "error", "code": "vibedata/bad-priority",
                          "message": f"{where}: logical source '{src_name}' priority_group "
                                     "must be an integer >= 0 (0 = preferred aggregate)"})
        grain = src.get("content_grain", [])
        if not isinstance(grain, list) or not all(isinstance(g, str) for g in grain):
            diags.append({"severity": "error", "code": "vibedata/bad-grain",
                          "message": f"{where}: logical source '{src_name}' content_grain "
                                     "must be a list of grain column names"})
        if priority != 0:
            detail_present = True
        column_map = src.get("column_map") or {}
        if not column_map and not src.get("note"):
            diags.append({"severity": "error", "code": "vibedata/empty-column-map",
                          "message": f"{where}: logical source '{src_name}' maps nothing and "
                                     "carries no note; a tombstone must name its restore "
                                     "condition"})
        if src.get("physical_table") not in physical_tables:
            diags.append({"severity": "error", "code": "vibedata/lts-dangling-table",
                          "message": f"{where}: logical source '{src_name}' references unknown "
                                     f"physical table '{src.get('physical_table')}'"})
        for logical_col in (src.get("column_map", {}) or {}):
            if logical_col not in suppliable:
                diags.append({"severity": "error", "code": "vibedata/lts-unknown-field",
                              "message": f"{where}: logical source '{src_name}' maps "
                                         f"undeclared field or metric '{logical_col}'"})
            elif logical_col in fields:
                mapped_fields.add(logical_col)
                field_suppliers.setdefault(logical_col, []).append(priority)
            elif logical_col in metric_names and priority == 0:
                diags.append({"severity": "warning", "code": "vibedata/agg-metric-unverified",
                              "message": f"{where}: aggregate source '{src_name}' maps metric "
                                         f"'{logical_col}'; confirm the agg column computes the "
                                         "same filtered aggregation (e.g. a monthly total is "
                                         "not billable-filtered revenue)"})
    if sources:
        for orphan in sorted(fields - mapped_fields):
            diags.append({"severity": "error", "code": "vibedata/field-unmapped",
                          "message": f"{where}: field '{orphan}' is supplied by no logical source"})
        for field in sorted(mapped_fields):
            if all(p == 0 for p in field_suppliers.get(field, [])):
                diags.append({"severity": "error", "code": "vibedata/field-agg-only",
                              "message": f"{where}: field '{field}' is supplied only by "
                                         "aggregate (priority 0) sources; every field must be "
                                         "suppliable at detail grain"})
        if not detail_present:
            diags.append({"severity": "warning", "code": "vibedata/no-detail-source",
                          "message": f"{where}: no logical source with priority_group != 0; "
                                     "every field should be suppliable at detail grain"})
    return diags


def _validate_relationship(rel, model_name, dataset_names, physical_join_names):
    diags = []
    rel_name = rel.get("name", "<unnamed>")
    where = f"relationship '{rel_name}'"
    payloads = []
    for data in _extensions(rel):
        payload, errs = _decode(data, where)
        diags.extend(errs)
        if payload:
            payloads.append(payload)
    if len(payloads) > 1:
        diags.append({"severity": "error", "code": "vibedata/duplicate-entry",
                      "message": f"{where}: multiple VIBEDATA entries; keep exactly one"})
    for payload in payloads:
        diags.extend(_unknown_keys(payload, RELATIONSHIP_KEYS, where))
        join = payload.get("physical_join")
        if join and join not in physical_join_names:
            diags.append({"severity": "error", "code": "vibedata/join-dangling",
                          "message": f"{where}: physical_join '{join}' names no "
                                     "model-level physical join"})
        cardinality = payload.get("cardinality")
        if cardinality and cardinality not in CARDINALITIES:
            diags.append({"severity": "error", "code": "vibedata/bad-cardinality",
                          "message": f"{where}: cardinality '{cardinality}' must be one of "
                                     f"{sorted(CARDINALITIES)}"})
        if cardinality == "many-to-many":
            diags.append({"severity": "warning", "code": "vibedata/many-to-many",
                          "message": f"{where}: many-to-many has no core FK equivalent; "
                                     "consumers must resolve it through a bridge"})
    return diags

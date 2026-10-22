"""Structural checks over an Ossie model document (VIBEDATA part).

Runs after the vendored upstream `validate_document()`. Answers one question:
*is this document well-formed and fully resolved?* — every declared name exists,
every reference points at something declared, every payload uses the frozen key
set in the right shape.

It does not judge meaning. Whether a mapping is honest, whether every field is
supplied, whether an aggregate computes the same aggregation, and whether a
table's population matches the star's are content questions, reviewed by the
agent against the mart SQL (see `SKILL.md` and `references/`).

Pure functions: input is the parsed YAML dict, output is a list of diagnostics.
"""

import json

VENDOR = "VIBEDATA"

CARDINALITIES = {"many-to-one", "one-to-one", "many-to-many"}

MODEL_KEYS = {"vibedata_version", "physical_tables", "physical_joins"}
DATASET_KEYS = {"vibedata_version", "alias_of", "physical", "partitioned_by",
                "scd", "logical_sources", "hierarchies"}
RELATIONSHIP_KEYS = {"vibedata_version", "physical_join", "cardinality",
                     "join_type", "join_cost", "join_expression", "note"}
PHYSICAL_TABLE_KEYS = {"name", "source", "dbt_model", "table_type", "alias_of", "role", "note"}
PHYSICAL_JOIN_KEYS = {"name", "from", "to"}
LTS_KEYS = {"name", "physical_table", "priority_group", "content_grain",
            "where", "join_cost", "note", "column_map"}
HIERARCHY_KEYS = {"name", "levels"}
SCD_KEYS = {"type", "natural_key", "valid_from", "valid_to", "is_current",
            "open_ended_value"}


def _error(code, message):
    return {"severity": "error", "code": code, "message": message}


def _extensions(node):
    """The decoded VIBEDATA payloads on a model/dataset/relationship node."""
    out = []
    if not isinstance(node, dict):
        return out
    for ext in node.get("custom_extensions") or []:
        if isinstance(ext, dict) and ext.get("vendor_name") == VENDOR:
            out.append(ext.get("data"))
    return out


def _decode(data, where):
    try:
        payload = json.loads(data)
    except (TypeError, json.JSONDecodeError) as e:
        return None, [_error("vibedata/data-not-json",
                             f"{where}: VIBEDATA data is not valid JSON: {e}")]
    if not isinstance(payload, dict):
        return None, [_error("vibedata/data-not-object",
                             f"{where}: VIBEDATA data must be a JSON object")]
    return payload, []


def _model_payload(model):
    """Model-level VIBEDATA payload. Duplicates are an error, not a merge."""
    diags = []
    raws = _extensions(model)
    if len(raws) > 1:
        diags.append(_error("vibedata/duplicate-entry",
                            "model: multiple VIBEDATA entries; keep exactly one"))
    merged = {}
    for data in raws:
        payload, errs = _decode(data, "model")
        diags.extend(errs)
        if payload:
            merged.update(payload)
    return merged, diags


def _unknown_keys(payload, allowed, where):
    return [_error("vibedata/unknown-key",
                   f"{where}: unknown VIBEDATA key '{k}'")
            for k in payload if k not in allowed]


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


def physical_table_index(doc):
    """Model-level physical tables by name: identity fields used for drift checks."""
    payload, _ = _model_payload(doc)
    out = {}
    for t in payload.get("physical_tables", []):
        if isinstance(t, dict) and t.get("name"):
            out[t["name"]] = {k: t.get(k) for k in
                              ("source", "dbt_model", "table_type", "alias_of", "role")}
    return out


def validate_vibedata(doc):
    """Structural VIBEDATA checks. Returns diagnostics."""
    diags = []
    if not isinstance(doc, dict) or "datasets" not in doc:
        return diags
    model_name = doc.get("name", "<unnamed>")

    versions = _collect_versions(doc)
    if any(v is None for v, _ in versions):
        diags.append(_error("vibedata/version-missing",
                            f"model '{model_name}': every VIBEDATA payload carries "
                            "vibedata_version"))
    elif len({v for v, _ in versions}) > 1:
        detail = ", ".join(f"{w}={v!r}" for v, w in versions)
        diags.append(_error("vibedata/version-mismatch",
                            f"model '{model_name}': mixed vibedata_version: {detail}"))

    model_payload, errs = _model_payload(doc)
    diags.extend(errs)
    diags.extend(_unknown_keys(model_payload, MODEL_KEYS, "model"))
    physical_tables = {t.get("name"): t
                       for t in model_payload.get("physical_tables", [])
                       if isinstance(t, dict) and t.get("name")}
    for t in model_payload.get("physical_tables", []):
        if not isinstance(t, dict) or not t.get("name"):
            diags.append(_error("vibedata/physical-table-nameless",
                                f"model '{model_name}': physical_tables entry without a name"))
            continue
        diags.extend(_unknown_keys(t, PHYSICAL_TABLE_KEYS, f"physical table '{t['name']}'"))
        alias_of = t.get("alias_of")
        if alias_of and (alias_of not in physical_tables or alias_of == t["name"]):
            diags.append(_error("vibedata/alias-dangling",
                                f"model '{model_name}': physical table '{t['name']}' is an "
                                f"alias of unknown table '{alias_of}'"))

    physical_join_names = set()
    for j in model_payload.get("physical_joins", []):
        if not isinstance(j, dict):
            diags.append(_error("vibedata/join-not-object",
                                f"model '{model_name}': physical join entry must be an object"))
            continue
        diags.extend(_unknown_keys(j, PHYSICAL_JOIN_KEYS,
                                   f"physical join '{j.get('name', '<unnamed>')}'"))
        physical_join_names.add(j.get("name"))
        for end in ("from", "to"):
            if j.get(end) not in physical_tables:
                diags.append(_error("vibedata/join-dangling",
                                    f"model '{model_name}': physical join "
                                    f"'{j.get('name', '<unnamed>')}' references unknown "
                                    f"physical table '{j.get(end)}'"))

    reached = {j.get("from") for j in model_payload.get("physical_joins", [])
               if isinstance(j, dict)}
    reached |= {j.get("to") for j in model_payload.get("physical_joins", [])
                if isinstance(j, dict)}
    for name in sorted(physical_tables):
        if name not in reached:
            diags.append({"severity": "warning", "code": "vibedata/table-unjoined",
                          "message": f"model '{model_name}': physical table '{name}' appears "
                                     "in no physical join"})

    dataset_names = {d.get("name") for d in doc.get("datasets", []) if d.get("name")}
    metric_names = {m.get("name") for m in doc.get("metrics", [])
                    if isinstance(m, dict) and m.get("name")}
    for dataset in doc.get("datasets", []):
        diags.extend(_validate_dataset(dataset, physical_tables, metric_names))
    for rel in doc.get("relationships", []):
        diags.extend(_validate_relationship(rel, dataset_names, physical_join_names))
        diags.extend(_validate_from_columns(rel, doc))
        diags.extend(_validate_to_columns(rel, doc))
    return diags


def _validate_dataset(dataset, physical_tables, metric_names):
    diags = []
    ds_name = dataset.get("name", "<unnamed>")
    where = f"dataset '{ds_name}'"
    fields = {f.get("name") for f in dataset.get("fields", []) if isinstance(f, dict)}
    for key_name, key_cols in (("primary_key", dataset.get("primary_key")),
                               ("unique_keys", dataset.get("unique_keys"))):
        groups = key_cols if key_name == "unique_keys" else [key_cols] if key_cols else []
        for group in groups or []:
            for col in group if isinstance(group, list) else []:
                if col not in fields:
                    diags.append(_error("vibedata/bad-key-column",
                                        f"{where}: {key_name} names '{col}', which is not a "
                                        "declared field"))
    payloads = []
    for data in _extensions(dataset):
        payload, errs = _decode(data, where)
        diags.extend(errs)
        if payload:
            payloads.append(payload)
    if len(payloads) > 1:
        diags.append(_error("vibedata/duplicate-entry",
                            f"{where}: multiple VIBEDATA entries; keep exactly one"))
    if not payloads:
        return diags
    if not (payload.get("logical_sources") or []):
        diags.append(_error("vibedata/lts-empty",
                            f"{where}: declares no logical source, so nothing supplies it"))
    payload = {}
    for p in payloads:
        payload.update(p)
    diags.extend(_unknown_keys(payload, DATASET_KEYS, where))

    alias_of = payload.get("alias_of")
    if alias_of and alias_of not in physical_tables:
        diags.append(_error("vibedata/alias-dangling",
                            f"{where}: alias_of unknown physical table '{alias_of}'"))

    for hier in payload.get("hierarchies", []):
        if not isinstance(hier, dict):
            diags.append(_error("vibedata/hierarchy-not-object",
                                f"{where}: hierarchy entry must be an object"))
            continue
        diags.extend(_unknown_keys(hier, HIERARCHY_KEYS,
                                   f"{where} hierarchy '{hier.get('name', '<unnamed>')}'"))
        for level in hier.get("levels", []) or []:
            if level not in fields:
                diags.append(_error("vibedata/hierarchy-unknown-field",
                                    f"{where}: hierarchy '{hier.get('name', '<unnamed>')}' "
                                    f"level '{level}' is not a declared field"))

    scd = payload.get("scd")
    if scd:
        if not isinstance(scd, dict):
            diags.append(_error("vibedata/scd-not-object", f"{where}: scd must be an object"))
            scd = {}
        diags.extend(_unknown_keys(scd, SCD_KEYS, f"{where} scd"))
        if scd.get("type") not in (1, 2, 3):
            diags.append(_error("vibedata/scd-bad-type",
                                f"{where}: scd.type must be 1, 2, or 3"))
        for key in ("natural_key", "valid_from", "valid_to", "is_current"):
            col = scd.get(key)
            if col and col not in fields:
                diags.append(_error("vibedata/scd-unknown-field",
                                    f"{where}: scd.{key} '{col}' is not a declared field"))

    partitioned_by = payload.get("partitioned_by")
    if partitioned_by is not None and (
            not isinstance(partitioned_by, list)
            or not all(isinstance(c, str) for c in partitioned_by)):
        diags.append(_error("vibedata/bad-partitioned-by",
                            f"{where}: partitioned_by must be a list of column names"))

    sources = payload.get("logical_sources", [])
    if not isinstance(sources, list):
        diags.append(_error("vibedata/lts-not-list",
                            f"{where}: logical_sources must be a list"))
        sources = []
    suppliable = fields | metric_names
    for src in sources:
        src_name = src.get("name", "<unnamed>") if isinstance(src, dict) else "<unnamed>"
        if not isinstance(src, dict):
            diags.append(_error("vibedata/lts-not-object",
                                f"{where}: logical source '{src_name}' must be an object"))
            continue
        diags.extend(_unknown_keys(src, LTS_KEYS, f"{where} logical source '{src_name}'"))
        priority = src.get("priority_group", 1)
        if not isinstance(priority, int) or isinstance(priority, bool) or priority < 0:
            diags.append(_error("vibedata/bad-priority",
                                f"{where}: logical source '{src_name}' priority_group "
                                "must be an integer >= 0"))
        grain = src.get("content_grain", [])
        if not isinstance(grain, list) or not all(isinstance(g, str) for g in grain):
            diags.append(_error("vibedata/bad-grain",
                                f"{where}: logical source '{src_name}' content_grain "
                                "must be a list of grain names"))
        if src.get("physical_table") not in physical_tables:
            diags.append(_error("vibedata/lts-dangling-table",
                                f"{where}: logical source '{src_name}' references unknown "
                                f"physical table '{src.get('physical_table')}'"))
        column_map = src.get("column_map", {}) or {}
        if not isinstance(column_map, dict):
            diags.append(_error("vibedata/bad-column-map",
                                f"{where}: logical source '{src_name}' column_map must be "
                                "an object of logical name to physical column"))
            column_map = {}
        for logical_col, physical_col in column_map.items():
            if logical_col not in suppliable:
                diags.append(_error("vibedata/lts-unknown-field",
                                    f"{where}: logical source '{src_name}' maps undeclared "
                                    f"field or metric '{logical_col}'"))
            if not isinstance(physical_col, str) or not physical_col:
                diags.append(_error("vibedata/bad-column-map",
                                    f"{where}: logical source '{src_name}' maps "
                                    f"'{logical_col}' to a non-string column"))
    return diags


def _validate_relationship(rel, dataset_names, physical_join_names):
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
        diags.append(_error("vibedata/duplicate-entry",
                            f"{where}: multiple VIBEDATA entries; keep exactly one"))
    for payload in payloads:
        diags.extend(_unknown_keys(payload, RELATIONSHIP_KEYS, where))
        join = payload.get("physical_join")
        if join and join not in physical_join_names:
            diags.append(_error("vibedata/join-dangling",
                                f"{where}: physical_join '{join}' names no model-level "
                                "physical join"))
        cardinality = payload.get("cardinality")
        if cardinality and cardinality not in CARDINALITIES:
            diags.append(_error("vibedata/bad-cardinality",
                                f"{where}: cardinality '{cardinality}' must be one of "
                                f"{sorted(CARDINALITIES)}"))
    return diags


def _validate_to_columns(rel, doc):
    """A relationship's to_columns must name fields the to dataset declares."""
    diags = []
    rel_name = rel.get("name", "<unnamed>")
    datasets = {d.get("name"): d for d in doc.get("datasets", []) if isinstance(d, dict)}
    target = datasets.get(rel.get("to"))
    columns = rel.get("to_columns")
    if not target or not isinstance(columns, list):
        return diags
    fields = {f.get("name") for f in target.get("fields", []) if isinstance(f, dict)}
    for column in columns:
        if column not in fields:
            diags.append(_error("relationship/to-column-unknown",
                                f"relationship '{rel_name}': to_column '{column}' is not a "
                                f"declared field of dataset '{rel.get('to')}'"))
    return diags


def _validate_from_columns(rel, doc):
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
            diags.append(_error("relationship/from-column-unknown",
                                f"relationship '{rel_name}': from_column '{column}' is not "
                                f"a declared field of dataset '{rel.get('from')}'"))
    return diags

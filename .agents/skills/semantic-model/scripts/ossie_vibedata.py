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
import re

VENDOR = "VIBEDATA"

CARDINALITIES = {"many-to-one", "one-to-one", "many-to-many"}
AGGREGATIONS = {"SUM", "MIN", "MAX", "NON_ADDITIVE"}
TIME_SERIES_FUNCTIONS = {"AGO", "TODATE"}

MODEL_KEYS = {"vibedata_version", "physical_tables", "physical_joins", "variables"}
DATASET_KEYS = {"vibedata_version", "alias_of", "physical", "partitioned_by",
                "scd", "logical_sources", "hierarchies"}
RELATIONSHIP_KEYS = {"vibedata_version", "physical_join", "cardinality",
                     "join_type", "join_cost", "join_expression", "note"}
PHYSICAL_TABLE_KEYS = {"name", "source", "dbt_model", "table_type", "alias_of", "role", "note"}
PHYSICAL_JOIN_KEYS = {"name", "from", "to"}
VARIABLE_KEYS = {"name", "datatype", "dbt_var", "note"}
LTS_KEYS = {"name", "physical_table", "priority_group", "content_grain",
            "content_levels", "content_filter", "navigable",
            "join_cost", "note", "column_map"}
HIERARCHY_KEYS = {"name", "is_time", "levels"}
LEVEL_KEYS = {"name", "key", "label"}
LEVEL_REF_KEYS = {"via", "hierarchy", "level"}
METRIC_KEYS = {"vibedata_version", "aggregation", "derived_expression", "at_levels",
               "time_series"}
TIME_SERIES_KEYS = {"function", "of", "via", "hierarchy", "level", "offset"}
SCD_KEYS = {"type", "natural_key", "valid_from", "valid_to", "is_current",
            "open_ended_value"}


# Words a predicate or post-aggregation formula may use that are not names.
SQL_WORDS = {"AND", "OR", "NOT", "IS", "NULL", "TRUE", "FALSE", "IN", "BETWEEN", "LIKE",
             "DATE", "TIMESTAMP", "CAST", "AS", "CASE", "WHEN", "THEN", "ELSE", "END",
             "NULLIF", "COALESCE"}
HELD_BY = re.compile(r"held by\s+[A-Za-z_][A-Za-z0-9_]*")


def _error(code, message):
    return {"severity": "error", "code": code, "message": message}


def _names_in(expression):
    """Bare identifiers and `:variable` references in a SQL snippet, literals removed."""
    text = re.sub(r"'(?:[^']|'')*'", " ", expression)
    variables = set(re.findall(r":([A-Za-z_][A-Za-z0-9_]*)", text))
    text = re.sub(r":[A-Za-z_][A-Za-z0-9_]*", " ", text)
    names = {n for n in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", text)
             if n.upper() not in SQL_WORDS}
    return names, variables


def _hierarchy_index(doc):
    """Hierarchies per dataset: {dataset: {hierarchy: {"is_time": bool, "levels": [...]}}}."""
    out = {}
    for dataset in doc.get("datasets", []):
        if not isinstance(dataset, dict):
            continue
        hierarchies = {}
        for data in _extensions(dataset):
            try:
                payload = json.loads(data)
            except (TypeError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict):
                continue
            for hier in payload.get("hierarchies") or []:
                if isinstance(hier, dict) and hier.get("name"):
                    hierarchies[hier["name"]] = {
                        "is_time": hier.get("is_time") is True,
                        "levels": [lv.get("name") for lv in hier.get("levels") or []
                                   if isinstance(lv, dict)]}
        out[dataset.get("name")] = hierarchies
    return out


def _check_level_ref(ref, where, relationships, hierarchies, from_dataset=None,
                     need_hierarchy=False):
    """A content or metric level: a relationship, and optionally a hierarchy level on its target.

    Omitting `hierarchy` and `level` means the target dataset's own key, the finest level.
    Returns (diagnostics, hierarchy info or None).
    """
    if not isinstance(ref, dict):
        return [_error("vibedata/level-ref-not-object", f"{where}: level entry must be an object")], None
    diags = _unknown_keys(ref, LEVEL_REF_KEYS, where)
    rel = relationships.get(ref.get("via"))
    if rel is None:
        return diags + [_error("vibedata/level-ref-unknown-relationship",
                               f"{where}: via '{ref.get('via')}' is not a relationship")], None
    if from_dataset is not None and rel.get("from") != from_dataset:
        diags.append(_error("vibedata/level-ref-wrong-dataset",
                            f"{where}: via '{ref.get('via')}' does not start at dataset "
                            f"'{from_dataset}'"))
    hier_name, level = ref.get("hierarchy"), ref.get("level")
    if hier_name is None and level is None:
        if need_hierarchy:
            diags.append(_error("vibedata/level-ref-needs-hierarchy",
                                f"{where}: names no hierarchy level"))
        return diags, None
    hier = hierarchies.get(rel.get("to"), {}).get(hier_name)
    if hier is None:
        diags.append(_error("vibedata/level-ref-unknown-hierarchy",
                            f"{where}: hierarchy '{hier_name}' is not declared on dataset "
                            f"'{rel.get('to')}'"))
        return diags, None
    if level not in hier["levels"]:
        diags.append(_error("vibedata/level-ref-unknown-level",
                            f"{where}: level '{level}' is not a level of hierarchy "
                            f"'{hier_name}'"))
    return diags, hier


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
    for metric in doc.get("metrics", []):
        grab(metric, f"metric '{metric.get('name', '<unnamed>')}'")
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

    variables = set()
    for var in model_payload.get("variables", []):
        if not isinstance(var, dict) or not var.get("name"):
            diags.append(_error("vibedata/variable-nameless",
                                f"model '{model_name}': variables entry without a name"))
            continue
        diags.extend(_unknown_keys(var, VARIABLE_KEYS, f"variable '{var['name']}'"))
        variables.add(var["name"])

    dataset_names = {d.get("name") for d in doc.get("datasets", []) if d.get("name")}
    metric_names = {m.get("name") for m in doc.get("metrics", [])
                    if isinstance(m, dict) and m.get("name")}
    context = {"physical_tables": physical_tables, "metric_names": metric_names,
               "variables": variables, "hierarchies": _hierarchy_index(doc),
               "relationships": {r.get("name"): r for r in doc.get("relationships", [])
                                 if isinstance(r, dict) and r.get("name")}}
    for dataset in doc.get("datasets", []):
        diags.extend(_validate_dataset(dataset, context))
    diags.extend(_validate_metrics(doc, context))
    for rel in doc.get("relationships", []):
        diags.extend(_validate_relationship(rel, dataset_names, physical_join_names))
        diags.extend(_validate_from_columns(rel, doc))
        diags.extend(_validate_to_columns(rel, doc))
    return diags


def _validate_dataset(dataset, context):
    physical_tables = context["physical_tables"]
    metric_names = context["metric_names"]
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
        hier_where = f"{where} hierarchy '{hier.get('name', '<unnamed>')}'"
        diags.extend(_unknown_keys(hier, HIERARCHY_KEYS, hier_where))
        level_names = set()
        for level in hier.get("levels", []) or []:
            if not isinstance(level, dict) or not level.get("name"):
                diags.append(_error("vibedata/level-not-object",
                                    f"{hier_where}: each level is an object with a name"))
                continue
            diags.extend(_unknown_keys(level, LEVEL_KEYS,
                                       f"{hier_where} level '{level['name']}'"))
            if level["name"] in level_names:
                diags.append(_error("vibedata/level-duplicate",
                                    f"{hier_where}: level '{level['name']}' appears twice"))
            level_names.add(level["name"])
            key = level.get("key")
            if not isinstance(key, list) or not key:
                diags.append(_error("vibedata/level-key-missing",
                                    f"{hier_where}: level '{level['name']}' needs a key: "
                                    "the fields that identify one member"))
                key = []
            for col in key + ([level["label"]] if level.get("label") else []):
                if col not in fields:
                    diags.append(_error("vibedata/hierarchy-unknown-field",
                                        f"{hier_where}: level '{level['name']}' names "
                                        f"'{col}', which is not a declared field"))

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
        for i, ref in enumerate(src.get("content_levels") or []):
            ref_diags, _ = _check_level_ref(
                ref, f"{where} logical source '{src_name}' content_levels[{i}]",
                context["relationships"], context["hierarchies"], from_dataset=ds_name)
            diags.extend(ref_diags)
        navigable = src.get("navigable", True)
        if not isinstance(navigable, bool):
            diags.append(_error("vibedata/bad-navigable",
                                f"{where}: logical source '{src_name}' navigable must be "
                                "true or false"))
        content_filter = src.get("content_filter")
        if content_filter is not None:
            diags.extend(_check_content_filter(content_filter, src, f"{where} logical source "
                                               f"'{src_name}'", fields, context["variables"]))
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


def _check_content_filter(content_filter, src, where, fields, variables):
    """A content filter is a predicate in the dataset's own fields, held by a test.

    A withdrawn source (empty column_map) binds nothing, so its filter needs no test.
    """
    if not isinstance(content_filter, str) or not content_filter.strip():
        return [_error("vibedata/bad-content-filter",
                       f"{where}: content_filter must be a non-empty SQL predicate")]
    diags = []
    names, refs = _names_in(content_filter)
    for name in sorted(names - fields):
        diags.append(_error("vibedata/content-filter-unknown-field",
                            f"{where}: content_filter names '{name}', which is not a "
                            "declared field of the dataset"))
    for ref in sorted(refs - variables):
        diags.append(_error("vibedata/content-filter-unknown-variable",
                            f"{where}: content_filter names ':{ref}', which is not a "
                            "declared model variable"))
    if src.get("column_map") and not HELD_BY.search(src.get("note") or ""):
        diags.append(_error("vibedata/content-filter-unheld",
                            f"{where}: a content_filter needs a note naming the test that "
                            "holds it ('held by <test>')"))
    return diags


def _metric_payload(metric, where):
    diags, payloads = [], []
    for data in _extensions(metric):
        payload, errs = _decode(data, where)
        diags.extend(errs)
        if payload:
            payloads.append(payload)
    if len(payloads) > 1:
        diags.append(_error("vibedata/duplicate-entry",
                            f"{where}: multiple VIBEDATA entries; keep exactly one"))
    merged = {}
    for p in payloads:
        merged.update(p)
    return merged, diags


def _validate_metrics(doc, context):
    """Rollup rule, post-aggregation formula, pinned levels and time series on metrics."""
    diags = []
    metrics = {m.get("name"): m for m in doc.get("metrics", [])
               if isinstance(m, dict) and m.get("name")}
    mapped = set()
    for dataset in doc.get("datasets", []):
        for data in _extensions(dataset):
            try:
                payload = json.loads(data)
            except (TypeError, json.JSONDecodeError):
                continue
            for src in (payload.get("logical_sources") or []) if isinstance(payload, dict) else []:
                if isinstance(src, dict) and isinstance(src.get("column_map"), dict):
                    mapped.update(src["column_map"])
    for name, metric in metrics.items():
        where = f"metric '{name}'"
        payload, errs = _metric_payload(metric, where)
        diags.extend(errs)
        if not payload:
            continue
        diags.extend(_unknown_keys(payload, METRIC_KEYS, where))
        aggregation = payload.get("aggregation")
        if aggregation is not None and aggregation not in AGGREGATIONS:
            diags.append(_error("vibedata/bad-aggregation",
                                f"{where}: aggregation '{aggregation}' must be one of "
                                f"{sorted(AGGREGATIONS)}"))
        derived = payload.get("derived_expression")
        if derived is not None:
            names, _ = _names_in(derived) if isinstance(derived, str) else (set(), set())
            if not isinstance(derived, str) or not names:
                diags.append(_error("vibedata/bad-derived-expression",
                                    f"{where}: derived_expression must be a formula over "
                                    "other metrics"))
            for ref in sorted(names - (set(metrics) - {name})):
                diags.append(_error("vibedata/derived-unknown-metric",
                                    f"{where}: derived_expression names '{ref}', which is "
                                    "not another metric of this model"))
            if name in mapped:
                diags.append(_error("vibedata/derived-metric-mapped",
                                    f"{where}: a post-aggregation metric is computed from "
                                    "its inputs and must not be bound to a column"))
        for i, ref in enumerate(payload.get("at_levels") or []):
            ref_diags, _ = _check_level_ref(ref, f"{where} at_levels[{i}]",
                                            context["relationships"], context["hierarchies"],
                                            need_hierarchy=True)
            diags.extend(ref_diags)
        series = payload.get("time_series")
        if series is not None:
            diags.extend(_check_time_series(series, name, metrics, where, context))
    return diags


def _check_time_series(series, name, metrics, where, context):
    if not isinstance(series, dict):
        return [_error("vibedata/bad-time-series", f"{where}: time_series must be an object")]
    diags = _unknown_keys(series, TIME_SERIES_KEYS, f"{where} time_series")
    function = series.get("function")
    if function not in TIME_SERIES_FUNCTIONS:
        diags.append(_error("vibedata/bad-time-series",
                            f"{where}: time_series.function must be one of "
                            f"{sorted(TIME_SERIES_FUNCTIONS)}"))
    base = metrics.get(series.get("of"))
    if base is None or series.get("of") == name:
        diags.append(_error("vibedata/time-series-unknown-metric",
                            f"{where}: time_series.of '{series.get('of')}' is not another "
                            "metric of this model"))
    elif json.dumps(base.get("expression"), sort_keys=True) != json.dumps(
            metrics[name].get("expression"), sort_keys=True):
        diags.append(_error("vibedata/time-series-expression",
                            f"{where}: expression must equal that of '{series.get('of')}', "
                            "the metric it shifts"))
    offset = series.get("offset")
    if function == "AGO" and (not isinstance(offset, int) or isinstance(offset, bool)
                              or offset < 1):
        diags.append(_error("vibedata/bad-time-series",
                            f"{where}: AGO needs an integer offset of at least 1"))
    if function == "TODATE" and offset is not None:
        diags.append(_error("vibedata/bad-time-series",
                            f"{where}: TODATE takes no offset"))
    ref = {k: series.get(k) for k in ("via", "hierarchy", "level")}
    ref_diags, hier = _check_level_ref(ref, f"{where} time_series", context["relationships"],
                                       context["hierarchies"], need_hierarchy=True)
    diags.extend(ref_diags)
    if hier is not None and not hier["is_time"]:
        diags.append(_error("vibedata/time-series-not-time",
                            f"{where}: hierarchy '{series.get('hierarchy')}' is not a time "
                            "hierarchy (is_time)"))
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

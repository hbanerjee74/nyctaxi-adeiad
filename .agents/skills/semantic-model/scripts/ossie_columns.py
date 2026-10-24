"""Check every physical column the model names against dbt's catalog.

`validate` cannot see the marts, so a `column_map` onto a column that does not exist
validates green. dbt's `catalog.json` (written by `dbt docs generate` against a built
warehouse) lists every relation's real columns. This module checks, per document:

- every physical table's `source` is a relation the catalog knows;
- every logical source's `column_map` targets a column of its physical table;
- every aggregate content level's `key_columns` are columns of the aggregate;
- every field expression reads only columns of its dataset's `source`.

Pure functions: input is parsed documents and the parsed catalog, output diagnostics.
"""

import json

import ossie_sql

VENDOR = "VIBEDATA"


def _payload(node):
    for ext in node.get("custom_extensions") or []:
        if isinstance(ext, dict) and ext.get("vendor_name") == VENDOR:
            try:
                data = json.loads(ext.get("data") or "{}")
            except json.JSONDecodeError:
                return {}
            return data if isinstance(data, dict) else {}
    return {}


def relations(catalog):
    """{'schema.name': {column, ...}} for every node and source in a dbt catalog."""
    out = {}
    for section in ("nodes", "sources"):
        for entry in (catalog.get(section) or {}).values():
            meta = entry.get("metadata") or {}
            if not meta.get("schema") or not meta.get("name"):
                continue
            columns = {(c.get("name") or key).lower()
                       for key, c in (entry.get("columns") or {}).items()}
            out[f"{meta['schema']}.{meta['name']}".lower()] = columns
    return out


def _error(code, message, where):
    return {"severity": "error", "code": code, "message": message, "file": where}


def check(doc, known, where):
    """Diagnostics for one document `doc` against catalog relations `known`."""
    diags = []
    model = _payload(doc)
    tables = {t["name"]: t for t in model.get("physical_tables") or [] if isinstance(t, dict)}

    def columns_of(source, what):
        key = (source or "").lower()
        if key not in known:
            diags.append(_error("columns/unknown-relation",
                                f"{what}: '{source}' is no relation in the catalog", where))
            return None
        return known[key]

    for name, table in sorted(tables.items()):
        columns_of(table.get("source"), f"physical table '{name}'")
    for dataset in doc.get("datasets") or []:
        ds = dataset.get("name", "<unnamed>")
        source_columns = columns_of(dataset.get("source"), f"dataset '{ds}'")
        for field in dataset.get("fields") or []:
            for dialect in (field.get("expression") or {}).get("dialects") or []:
                if dialect.get("dialect") not in ("ANSI_SQL", "OSSIE_SQL_2026"):
                    continue
                try:
                    read, _ = ossie_sql.names(dialect.get("expression"))
                except ossie_sql.ExpressionError:
                    continue  # validate reports an expression that does not parse
                for column in sorted(c for c in read if "." not in c):
                    if source_columns is not None and column not in source_columns:
                        diags.append(_error("columns/field-unknown-column",
                                            f"field '{ds}.{field.get('name')}' reads "
                                            f"'{column}', which '{dataset.get('source')}' "
                                            "does not have", where))
        for src in _payload(dataset).get("logical_sources") or []:
            table = tables.get(src.get("physical_table"))
            if table is None:
                continue
            what = f"logical source '{ds}.{src.get('name')}'"
            columns = columns_of(table.get("source"), what)
            if columns is None:
                continue
            for logical, physical in sorted((src.get("column_map") or {}).items()):
                if str(physical).lower() not in columns:
                    diags.append(_error("columns/map-unknown-column",
                                        f"{what} maps '{logical}' to '{physical}', which "
                                        f"'{table.get('source')}' does not have", where))
            for ref in src.get("content_levels") or []:
                for column in ref.get("key_columns") or []:
                    if str(column).lower() not in columns:
                        diags.append(_error("columns/key-unknown-column",
                                            f"{what} carries the {ref.get('via')} key in "
                                            f"'{column}', which '{table.get('source')}' does "
                                            "not have", where))
    return diags

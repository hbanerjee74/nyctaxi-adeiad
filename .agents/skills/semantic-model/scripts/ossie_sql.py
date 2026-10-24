"""The one SQL expression layer every other tool uses, aligned with Ossie's own.

Every predicate (`content_filter`, `join_expression`, a query filter) and formula
(`derived_expression`, a metric's core expression) is checked here exactly as Apache
Ossie checks a core expression: by the vendored `validate_sql_expression`, with the
same sqlglot dialect mapping and the same single-expression rule. It is then parsed in
that generic (OSSIE_SQL_2026 / ANSI) dialect, and unquoted identifiers are normalised,
because the Ossie expression language makes them case-insensitive.

One thing goes beyond Ossie's grammar: compiled SQL is rendered for DuckDB, the engine
the generated tests run on. A `:name` placeholder parses, but nothing may use one yet:
the validator reports it, and `rewrite` refuses it.
"""

import importlib.util
from pathlib import Path

import sqlglot
from sqlglot import exp
from sqlglot.optimizer.normalize_identifiers import normalize_identifiers

TARGET = "duckdb"
OSSIE_DIALECT = "OSSIE_SQL_2026"

_spec = importlib.util.spec_from_file_location(
    "ossie_vendor_validate_sql",
    Path(__file__).parent / "ossie_vendor" / "validation" / "validate.py")
_vendor = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_vendor)


class ExpressionError(ValueError):
    """An expression Ossie's own check rejects, or that does not parse."""


def parse(text):
    """Check `text` as Ossie does, then parse it with unquoted identifiers normalised."""
    if not isinstance(text, str) or not text.strip():
        raise ExpressionError("empty expression")
    error = _vendor.validate_sql_expression(text, OSSIE_DIALECT, "expression")
    if error:
        raise ExpressionError(error.replace("[SQL] expression: ", ""))
    try:
        node = sqlglot.parse_one(text)
    except sqlglot.errors.SqlglotError as e:
        raise ExpressionError(str(e).splitlines()[0]) from e
    if node is None:
        raise ExpressionError("empty expression")
    return normalize_identifiers(node)


def names(text):
    """(column names, :placeholder names) an expression reads. Qualified columns keep 'table.name'."""
    node = parse(text)
    columns = {f"{c.table}.{c.name}" if c.table else c.name for c in node.find_all(exp.Column)}
    variables = {p.name for p in node.find_all(exp.Placeholder) if p.name}
    return columns, variables


def conjuncts(text):
    """The canonical AND-ed terms of a predicate; None or empty text is no condition.

    Keywords, spacing and unquoted identifier case are normalised, so two spellings of
    one condition compare equal. Terms render in the generic dialect.
    """
    if text is None or not str(text).strip():
        return []
    node = parse(text)
    terms = node.flatten() if isinstance(node, exp.And) else [node]
    return [term.sql() for term in terms]


def rewrite(text, column=None, name=None):
    """Return `text` as DuckDB SQL with columns and bare names replaced.

    `column(table, name)` returns replacement SQL for a column reference (or None to
    keep it); `name(identifier)` handles unqualified columns that stand for another
    object (a metric in a formula). A `:placeholder` raises ExpressionError.
    """
    node = parse(text)

    def swap(n):
        if isinstance(n, exp.Placeholder):
            raise ExpressionError(f"':{n.name}' is a variable; variables are not supported yet")
        if isinstance(n, exp.Column):
            replacement = None
            if not n.table and name is not None:
                replacement = name(n.name)
            if replacement is None and column is not None:
                replacement = column(n.table or None, n.name)
            if replacement is not None:
                return exp.paren(sqlglot.parse_one(replacement, dialect=TARGET), copy=False)
        return n

    return node.transform(swap).sql(dialect=TARGET)

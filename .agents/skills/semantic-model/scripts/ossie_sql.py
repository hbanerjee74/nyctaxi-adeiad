"""The one SQL expression layer every other tool uses (sqlglot).

Predicates (`content_filter`, a query filter) and formulas (`derived_expression`, a
metric's core expression) are parsed here and nowhere else, so the validator, the
compiler and the generated tests agree on what an expression names and means.
"""

import sqlglot
from sqlglot import exp

DIALECT = "duckdb"


class ExpressionError(ValueError):
    """An expression that does not parse."""


def parse(text):
    """Parse one SQL expression; raise ExpressionError when it does not parse."""
    if not isinstance(text, str) or not text.strip():
        raise ExpressionError("empty expression")
    try:
        node = sqlglot.parse_one(text, dialect=DIALECT)
    except sqlglot.errors.SqlglotError as e:
        raise ExpressionError(str(e).splitlines()[0]) from e
    if node is None:
        raise ExpressionError("empty expression")
    return node


def names(text):
    """(column names, :variable names) an expression reads. Qualified columns keep 'table.name'."""
    node = parse(text)
    columns = {f"{c.table}.{c.name}" if c.table else c.name for c in node.find_all(exp.Column)}
    variables = {p.name for p in node.find_all(exp.Placeholder) if p.name}
    return columns, variables


def conjuncts(text):
    """The canonical AND-ed terms of a predicate; None or empty text is no condition.

    Keywords and spacing are normalised; identifiers stay case-sensitive. Terms render
    in the generic dialect, so a :variable reads as written.
    """
    if text is None or not str(text).strip():
        return []
    node = parse(text)
    terms = node.flatten() if isinstance(node, exp.And) else [node]
    return [term.sql() for term in terms]


def rewrite(text, column=None, variable=None, name=None):
    """Return `text` as SQL with columns, :variables and bare names replaced.

    `column(table, name)` returns replacement SQL for a column reference (or None to
    keep it); `variable(name)` returns SQL for a :variable; `name(identifier)` handles
    unqualified columns that stand for another object (a metric in a formula).
    """
    node = parse(text)

    def swap(n):
        if isinstance(n, exp.Placeholder) and variable is not None:
            return sqlglot.parse_one(variable(n.name), dialect=DIALECT)
        if isinstance(n, exp.Column):
            replacement = None
            if not n.table and name is not None:
                replacement = name(n.name)
            if replacement is None and column is not None:
                replacement = column(n.table or None, n.name)
            if replacement is not None:
                return exp.paren(sqlglot.parse_one(replacement, dialect=DIALECT), copy=False)
        return n

    return node.transform(swap).sql(dialect=DIALECT)

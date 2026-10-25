"""The ingest pipelines freeze every resource against the columns its contract declares.

These tests build their pipelines from the repo root, so `ingestion/.dlt/config.toml` is not
loaded and dlt's default snake_case naming applies here. Production runs from `ingestion/`, where
`[schema] naming = "direct"` keeps `LocationID` exactly as written. Do not "correct" a CamelCase
contract property to snake_case on the strength of this file: under direct naming that creates a
second column instead of renaming one.
"""

from types import SimpleNamespace

import dlt
import duckdb
import pytest
from dlt.common.normalizers.naming.snake_case import NamingConvention
from dlt.pipeline.exceptions import PipelineStepFailed

import mdm_pipeline
import ops_pipeline
import tlc_pipeline
from contracts import COLUMNS
from sources import mdm, ops

TLC_TABLES = ("yellow_tripdata", "green_tripdata", "taxi_zone_lookup")
ZONES = [{"LocationID": 1, "Borough": "EWR", "Zone": "Newark Airport", "service_zone": "EWR"}]


class _Factory:
    """Stands in for a `@dlt.source` factory, which main clones and then calls."""

    def __init__(self, source):
        self.source = source

    def clone(self, **kwargs):
        return self

    def __call__(self, **kwargs):
        return self.source


def _one_resource(name, rows):
    @dlt.source(name="test")
    def source():
        @dlt.resource(name=name)
        def table():
            yield from rows

        return table

    return source()


class _Recorder:
    """A pipeline that records the source main hands it instead of loading it."""

    source = None

    def run(self, source):
        self.source = source
        return "load-info"


def _no_load(monkeypatch, module, pipeline):
    """Keep main offline: no environment probe, no audit write, no destination."""
    monkeypatch.setattr(module, "setup_environment", lambda: None)
    monkeypatch.setattr(module, "finalize", lambda *args, **kwargs: {})
    monkeypatch.setattr(module, "dlt", SimpleNamespace(pipeline=pipeline))


def _destination(tmp_path):
    """A pipeline factory writing the warehouse and its state under `tmp_path`."""
    database = tmp_path / "test.duckdb"

    def pipeline(**settings):
        settings["destination"] = dlt.destinations.duckdb(credentials=str(database))
        settings["pipelines_dir"] = str(tmp_path / "pipelines")
        return dlt.pipeline(**settings)

    return database, pipeline


def _columns(database, schema, table):
    con = duckdb.connect(str(database))
    try:
        rows = con.execute(
            "select column_name from information_schema.columns "
            "where table_schema = ? and table_name = ?",
            [schema, table],
        ).fetchall()
    finally:
        con.close()
    return [row[0] for row in rows]


def test_a_resource_matching_its_contract_loads(tmp_path, monkeypatch):
    database, pipeline = _destination(tmp_path)
    _no_load(monkeypatch, tlc_pipeline, pipeline)
    monkeypatch.setattr(
        tlc_pipeline, "tlc_source", _Factory(_one_resource("taxi_zone_lookup", ZONES))
    )

    tlc_pipeline.main()

    con = duckdb.connect(str(database))
    try:
        loaded = con.execute("select location_id, borough from bronze.taxi_zone_lookup").fetchall()
    finally:
        con.close()
    assert loaded == [(1, "EWR")]
    declared = {NamingConvention().normalize_identifier(c) for c in COLUMNS["taxi_zone_lookup"]}
    assert declared <= set(_columns(database, "bronze", "taxi_zone_lookup"))


def test_an_undeclared_column_violates_the_contract(tmp_path, monkeypatch):
    """The first run declares the table; the stored schema is what `freeze` compares against."""
    database, pipeline = _destination(tmp_path)
    _no_load(monkeypatch, tlc_pipeline, pipeline)
    monkeypatch.setattr(
        tlc_pipeline, "tlc_source", _Factory(_one_resource("taxi_zone_lookup", ZONES))
    )
    tlc_pipeline.main()

    extra = [{**ZONES[0], "surprise": "undeclared"}]
    monkeypatch.setattr(
        tlc_pipeline, "tlc_source", _Factory(_one_resource("taxi_zone_lookup", extra))
    )
    with pytest.raises(PipelineStepFailed) as excinfo:
        tlc_pipeline.main()

    message = str(excinfo.value)
    assert "surprise" in message
    assert "contract_mode=freeze" in message
    assert "surprise" not in _columns(database, "bronze", "taxi_zone_lookup")


@pytest.mark.parametrize(
    "module,tables",
    [
        (tlc_pipeline, TLC_TABLES),
        (ops_pipeline, tuple(ops.TABLES)),
        (mdm_pipeline, tuple(mdm.SQL)),
    ],
)
def test_every_selected_resource_carries_its_contract_columns(module, tables, monkeypatch):
    """main hands the loader the real resource set, each hinted from the generated contract."""
    recorder = _Recorder()
    _no_load(monkeypatch, module, lambda **settings: recorder)
    # mdm reads the zone lookup while the source is built, before the pipeline sees it.
    monkeypatch.setattr(mdm_pipeline, "zone_rows", lambda: [])

    module.main()

    assert set(recorder.source.selected_resources) == set(tables)
    hinted = {
        name: {column: hint["data_type"] for column, hint in resource.columns.items()}
        for name, resource in recorder.source.selected_resources.items()
    }
    assert hinted == {
        name: {column: hint["data_type"] for column, hint in COLUMNS[name].items()}
        for name in tables
    }


def test_a_resource_with_no_contract_columns_refuses_to_load(monkeypatch):
    _no_load(monkeypatch, ops_pipeline, lambda **settings: _Recorder())
    monkeypatch.setattr(ops_pipeline, "ops_source", _Factory(_one_resource("uncontracted", [])))

    with pytest.raises(KeyError, match="uncontracted"):
        ops_pipeline.main()

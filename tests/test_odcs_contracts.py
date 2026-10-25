"""Both enforcement paths refuse a column the contract does not declare.

The dlt half freezes every resource against `COLUMNS`; the dbt half runs a real build of one
enforced-contract model in a scratch copy of the project.

The ingest tests build their pipelines from the repo root, so `ingestion/.dlt/config.toml` is not
loaded and dlt's default snake_case naming applies here. Production runs from `ingestion/`, where
`[schema] naming = "direct"` keeps `LocationID` exactly as written. Do not "correct" a CamelCase
contract property to snake_case on the strength of this file: under direct naming that creates a
second column instead of renaming one.
"""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
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

ROOT = Path(__file__).resolve().parents[1]
TLC_TABLES = ("yellow_tripdata", "green_tripdata", "taxi_zone_lookup")
ZONES = [{"LocationID": 1, "Borough": "EWR", "Zone": "Newark Airport", "service_zone": "EWR"}]
DBT = [sys.executable, "-m", "dbt.cli.main"]


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
            "where table_schema = ? and table_name = ? "
            "order by ordinal_position",
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
    # The violation is a rejection, not a partial load: the first load stands, and `surprise`
    # is in no relation.
    con = duckdb.connect(str(database))
    try:
        loaded = con.execute("select location_id, borough from bronze.taxi_zone_lookup").fetchall()
    finally:
        con.close()
    assert loaded == [(1, "EWR")]
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


# ---------------------------------------------------------------------------
# dbt: an enforced contract is what makes an undeclared model column a failure
# ---------------------------------------------------------------------------


def _scratch_project(tmp_path):
    """A copy of the dbt project. The demonstration edits this, never the tree under test.

    The copy carries `dbt_packages`; on a fresh checkout they are installed first, as
    `tests/test_maps.py` does, because `dbt` refuses to run without them.
    """
    source = ROOT / "transformation"
    if not (source / "dbt_packages").exists():
        subprocess.run(
            [*DBT, "deps", "--profiles-dir", str(source), "--profile", "nyc_taxi_analytics"],
            cwd=source,
            env={**os.environ, "VD_EPHM_DUCKDB_LOCAL_PATH": str(tmp_path / "deps.duckdb")},
            capture_output=True,
            check=True,
        )
    project = tmp_path / "transformation"
    shutil.copytree(source, project, ignore=shutil.ignore_patterns("target", "logs"))
    return project


def _dbt_build(project, warehouse):
    """Build one seed and one enforced-contract model into `warehouse`.

    Singular tests are excluded because they read the whole warehouse, and this fixture builds
    neither the sources nor the rest of the models.
    """
    return subprocess.run(
        [
            *DBT,
            "build",
            "--select",
            "+dim_daypart",
            "--exclude",
            "test_type:singular",
            "--profiles-dir",
            str(project),
            "--profile",
            "nyc_taxi_analytics",
        ],
        cwd=project,
        env={**os.environ, "VD_EPHM_DUCKDB_LOCAL_PATH": str(warehouse)},
        capture_output=True,
        text=True,
    )


def test_a_model_column_absent_from_its_contract_fails_the_build(tmp_path):
    """`dim_daypart` is one seed away from nothing, so the build is cheap; its contract is real."""
    project = _scratch_project(tmp_path)
    warehouse = tmp_path / "warehouse.duckdb"
    model = project / "models/marts/core/dim_daypart.sql"
    # dbt enforces the generated `data_type` and column list here; `odcs.py check` owns the
    # contract-to-key wiring, so this file is the half the build reads.
    contract = project / "models/marts/core/_core.yml"

    clean = _dbt_build(project, warehouse)
    assert clean.returncode == 0, clean.stdout + clean.stderr
    assert _columns(warehouse, "core", "dim_daypart") == [
        "hour_of_day",
        "daypart_code",
        "daypart_name",
        "is_peak",
    ]

    declared = model.read_text()
    extra_column = "    is_peak,\n    upper(daypart_code) as daypart_code_upper\n"
    model.write_text(declared.replace("    is_peak\n", extra_column))
    assert "daypart_code_upper" not in contract.read_text()

    drift = _dbt_build(project, warehouse)
    output = drift.stdout + drift.stderr
    assert drift.returncode != 0
    assert "This model has an enforced contract that failed" in output
    # The column, and the reason, on the same row of dbt's mismatch table.
    assert re.search(r"\|\s*daypart_code_upper\s*\|.*\|\s*missing in contract\s*\|", output)


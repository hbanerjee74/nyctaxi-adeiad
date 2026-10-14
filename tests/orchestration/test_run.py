from pathlib import Path
from types import SimpleNamespace

import run_all
import run_ingest
import run_transform

ROOT = Path(__file__).resolve().parents[2]


class Recorder:
    def __init__(self, fail_on=None):
        self.calls = []
        self.fail_on = fail_on

    def __call__(self, command, cwd, env):
        self.calls.append((list(command), Path(cwd), dict(env)))
        failed = self.fail_on is not None and self.fail_on in " ".join(command)
        return SimpleNamespace(returncode=1 if failed else 0)


def test_ingest_runs_tlc_then_ops_then_mdm_from_the_ingestion_root():
    runner = Recorder()
    assert run_ingest.run_ingest(runner) == 0
    scripts = [Path(c[-1]).name for c, _, _ in runner.calls]
    assert scripts == ["tlc_pipeline.py", "ops_pipeline.py", "mdm_pipeline.py"]
    assert {cwd for _, cwd, _ in runner.calls} == {ROOT / "ingestion"}


def test_ingest_environment_points_at_the_repo_database():
    runner = Recorder()
    run_ingest.run_ingest(runner)
    for _, _, env in runner.calls:
        assert env["VD_EPHM_DUCKDB_LOCAL_PATH"] == str(ROOT / "domain.duckdb")
        assert env["VD_DOMAIN_DATA_PLATFORM"] == "duckdb_local"
        assert env["VD_DOMAIN_SECRET_STORE_KIND"] == "local_toml"


def test_ingest_stops_at_the_first_failing_pipeline():
    runner = Recorder(fail_on="ops_pipeline.py")
    assert run_ingest.run_ingest(runner) == 1
    assert [Path(c[-1]).name for c, _, _ in runner.calls] == ["tlc_pipeline.py", "ops_pipeline.py"]


def test_transform_runs_dbt_build_against_the_domain_target():
    runner = Recorder()
    assert run_transform.run_transform(runner) == 0
    (command, cwd, _), = runner.calls
    assert command[-3:] == ["build", "--target", "domain"]
    assert cwd == ROOT / "transformation"


def test_all_does_not_run_dbt_when_ingestion_fails():
    runner = Recorder(fail_on="mdm_pipeline.py")
    assert run_all.run_all(runner) == 1
    assert not any("dbt" in " ".join(c) for c, _, _ in runner.calls)

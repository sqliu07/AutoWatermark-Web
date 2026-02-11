import pathlib
import sys
from datetime import datetime

import pytest
import logging

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

_logger = logging.getLogger("tests")
LOG_DIR = PROJECT_ROOT / "logs" / "citest"
RESULTS = {}


def _next_log_path():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_numbers = []
    for path in LOG_DIR.glob("pytest_*_run*.log"):
        stem = path.stem
        if "_run" not in stem:
            continue
        try:
            run_numbers.append(int(stem.rsplit("_run", 1)[1]))
        except ValueError:
            continue

    run_index = max(run_numbers, default=0) + 1
    filename = f"pytest_{timestamp}_run{run_index:03d}.log"
    return LOG_DIR / filename


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    config.option.log_file = str(_next_log_path())
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    _logger.info("LOGFILE %s", config.option.log_file)


def pytest_runtest_logstart(nodeid, location):
    _logger.info("START %s", nodeid)


def _result_label(report):
    if report.outcome == "passed":
        return "PASS"
    if report.outcome == "failed":
        return "FAIL"
    if report.outcome == "skipped":
        return "XFAIL" if hasattr(report, "wasxfail") else "SKIP"
    return report.outcome.upper()


def pytest_runtest_logreport(report):
    if report.when != "call":
        if report.outcome == "failed":
            _logger.info("ERROR %s (%s)", report.nodeid, report.when)
            RESULTS.setdefault(report.nodeid, "failed")
        return

    RESULTS[report.nodeid] = report.outcome
    _logger.info("%s %s", _result_label(report), report.nodeid)


def pytest_sessionfinish(session, exitstatus):
    passed = sum(1 for outcome in RESULTS.values() if outcome == "passed")
    failed = sum(1 for outcome in RESULTS.values() if outcome == "failed")
    total = passed + failed
    _logger.info("PASS:%s,FAIL:%s,TOTAL:%s", passed, failed, total)

from app_factory import create_app
from config.settings import AppConfig


@pytest.fixture
def app(tmp_path):
    upload_dir = tmp_path / "uploads"
    config = AppConfig()
    config.upload_folder = upload_dir
    config.start_background_cleaner = False
    app = create_app(config)
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()

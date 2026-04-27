import os
from pathlib import Path

import pytest

# ── 加载 .env ─────────────────────────────────────────────────────────────
_env_file = Path(__file__).parent / ".env"
if _env_file.exists():
    for _line in _env_file.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())


# ── pytest-html 自定义列：Module / Owner ──────────────────────────────────

def pytest_html_results_table_header(cells):
    cells.insert(2, "<th>Project</th>")
    cells.insert(3, "<th>Module</th>")
    cells.insert(4, "<th>Owner</th>")


def pytest_html_results_table_row(report, cells):
    cells.insert(2, f"<td>{getattr(report, 'nl_project', '-')}</td>")
    cells.insert(3, f"<td>{getattr(report, 'nl_module', '-')}</td>")
    cells.insert(4, f"<td>{getattr(report, 'nl_owner', '-')}</td>")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()

    p = item.get_closest_marker("project")
    m = item.get_closest_marker("module")
    o = item.get_closest_marker("owner")
    report.nl_project = p.args[0] if p else "-"
    report.nl_module = m.args[0] if m else "-"
    report.nl_owner = o.args[0] if o else "-"
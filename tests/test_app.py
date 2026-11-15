"""Smoke test of the Streamlit app (skipped when app/data has not been exported)."""

from pathlib import Path

import pytest

DATA = Path(__file__).resolve().parents[1] / "app" / "data" / "signals.parquet"
pytest.importorskip("streamlit")


@pytest.mark.skipif(not DATA.exists(), reason="app data not exported")
def test_app_runs_without_errors():
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(str(DATA.parents[1] / "app.py"), default_timeout=120).run()
    assert not app.exception
    assert app.title[0].value == "FAERS signal explorer"
    app.selectbox[0].set_value("SEMAGLUTIDE").run()
    assert not app.exception

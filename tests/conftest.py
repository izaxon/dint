from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolated_webhook_secret(monkeypatch):
    # runtime.ensure_webhook_secret() writes the generated secret into os.environ.
    # Clearing it through monkeypatch makes that write undo itself after each test.
    monkeypatch.delenv("LOGBOOK_WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("DINT_WEBHOOK_SECRET", raising=False)

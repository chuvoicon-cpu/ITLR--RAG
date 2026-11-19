import pytest
from fastapi import HTTPException

from itlr.api.ratelimit import acquire_chat_slot


def test_chat_slots_respond_with_backpressure_and_can_be_reused(monkeypatch):
    monkeypatch.setenv("ITLR_CHAT_CONCURRENCY", "1")
    release = acquire_chat_slot()
    try:
        with pytest.raises(HTTPException) as busy:
            acquire_chat_slot()
        assert busy.value.status_code == 429
    finally:
        release()
    acquire_chat_slot()()

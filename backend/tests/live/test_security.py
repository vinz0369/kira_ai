import uuid

from app.live.security import TicketStore, hash_overlay_key, overlay_key_matches


def test_overlay_key_is_hashed_and_constant_time_checked() -> None:
    secret = "not-saved-in-plain-text"
    hashed = hash_overlay_key(secret)
    assert secret not in hashed
    assert overlay_key_matches(secret, hashed)
    assert not overlay_key_matches("wrong", hashed)


def test_ws_ticket_is_single_use_and_session_scoped() -> None:
    store = TicketStore()
    session_id = uuid.uuid4()
    user_id = uuid.uuid4()
    ticket = store.issue(session_id, user_id)
    assert store.consume(ticket, uuid.uuid4()) is None
    ticket = store.issue(session_id, user_id)
    assert store.consume(ticket, session_id) is not None
    assert store.consume(ticket, session_id) is None

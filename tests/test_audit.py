from sqlalchemy import update

from verification_core import audit
from verification_core.db import make_engine, make_sessionmaker
from verification_core.models import AuditEvent, Base


def _plain_session(tmp_path):
    # Schema without triggers, to simulate an attacker with raw database access.
    engine = make_engine(f"sqlite:///{tmp_path / 'plain.db'}")
    Base.metadata.create_all(engine)
    return make_sessionmaker(engine)


def _fill(session, n=3):
    for i in range(n):
        audit.append(
            session,
            event_type="TEST",
            actor_type="test",
            actor_id="t",
            object_type="thing",
            object_id=str(i),
            payload={"i": i},
        )


def test_chain_verifies(tmp_path):
    factory = _plain_session(tmp_path)
    with factory.begin() as s:
        _fill(s)
    with factory() as s:
        ok, findings = audit.verify_chain(s)
        assert ok, findings
        assert audit.head(s).sequence == 3


def test_edited_payload_is_detected(tmp_path):
    factory = _plain_session(tmp_path)
    with factory.begin() as s:
        _fill(s)
    with factory.begin() as s:
        s.execute(
            update(AuditEvent).where(AuditEvent.sequence == 2).values(event_payload={"i": 99})
        )
    with factory() as s:
        ok, findings = audit.verify_chain(s)
        assert not ok
        assert any("sequence 2" in f for f in findings)


def test_deleted_event_is_detected(tmp_path):
    factory = _plain_session(tmp_path)
    with factory.begin() as s:
        _fill(s)
    with factory.begin() as s:
        s.query(AuditEvent).filter(AuditEvent.sequence == 2).delete()
    with factory() as s:
        ok, findings = audit.verify_chain(s)
        assert not ok

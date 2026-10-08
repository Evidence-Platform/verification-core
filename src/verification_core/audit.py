"""Hash-chained, append-only audit log.

event_hash = SHA-256(JCS({sequence, event_type, actor, object, payload, previous_event_hash,
created_at})). Removing, reordering or editing any event breaks every later hash. Publishing
the latest head (sequence + hash) externally, e.g. in a transparency log, lets third parties
detect a rewritten history.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import iso
from .hashing import canonical_sha256
from .models import AuditEvent, utcnow

GENESIS_HASH = "0" * 64


def _event_digest(
    *,
    sequence: int,
    event_type: str,
    actor_type: str,
    actor_id: str,
    object_type: str,
    object_id: str,
    payload: dict[str, Any],
    previous_event_hash: str,
    created_at: datetime,
) -> str:
    return canonical_sha256(
        {
            "sequence": sequence,
            "event_type": event_type,
            "actor_type": actor_type,
            "actor_id": actor_id,
            "object_type": object_type,
            "object_id": object_id,
            "payload": payload,
            "previous_event_hash": previous_event_hash,
            "created_at": iso(created_at),
        }
    )


def head(session: Session) -> AuditEvent | None:
    return session.scalars(select(AuditEvent).order_by(AuditEvent.sequence.desc()).limit(1)).first()


def append(
    session: Session,
    *,
    event_type: str,
    actor_type: str,
    actor_id: str,
    object_type: str,
    object_id: str,
    payload: dict[str, Any] | None = None,
) -> AuditEvent:
    """Append an event. A unique constraint on ``sequence`` rejects concurrent writers;
    the caller retries the whole transaction in that case."""
    last = head(session)
    sequence = 1 if last is None else last.sequence + 1
    previous = GENESIS_HASH if last is None else last.event_hash
    created_at = utcnow()
    payload = payload or {}
    event = AuditEvent(
        sequence=sequence,
        event_type=event_type,
        actor_type=actor_type,
        actor_id=actor_id,
        object_type=object_type,
        object_id=object_id,
        event_payload=payload,
        previous_event_hash=previous,
        created_at=created_at,
        event_hash=_event_digest(
            sequence=sequence,
            event_type=event_type,
            actor_type=actor_type,
            actor_id=actor_id,
            object_type=object_type,
            object_id=object_id,
            payload=payload,
            previous_event_hash=previous,
            created_at=created_at,
        ),
    )
    session.add(event)
    session.flush()
    return event


def verify_chain(session: Session) -> tuple[bool, list[str]]:
    """Recompute the whole chain. Returns (ok, list of findings)."""
    findings: list[str] = []
    expected_previous = GENESIS_HASH
    expected_sequence = 1
    for ev in session.scalars(select(AuditEvent).order_by(AuditEvent.sequence)):
        if ev.sequence != expected_sequence:
            findings.append(f"gap: expected sequence {expected_sequence}, found {ev.sequence}")
        if ev.previous_event_hash != expected_previous:
            findings.append(f"broken link at sequence {ev.sequence}")
        recomputed = _event_digest(
            sequence=ev.sequence,
            event_type=ev.event_type,
            actor_type=ev.actor_type,
            actor_id=ev.actor_id,
            object_type=ev.object_type,
            object_id=ev.object_id,
            payload=ev.event_payload,
            previous_event_hash=ev.previous_event_hash,
            created_at=ev.created_at,
        )
        if recomputed != ev.event_hash:
            findings.append(f"hash mismatch at sequence {ev.sequence}")
        expected_previous = ev.event_hash
        expected_sequence = ev.sequence + 1
    return (not findings, findings)

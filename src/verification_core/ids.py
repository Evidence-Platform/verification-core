"""Identifier helpers. All primary keys are UUIDv7 (time ordered, see ADR-0004)."""

import uuid

import uuid_utils


def new_id() -> uuid.UUID:
    return uuid.UUID(str(uuid_utils.uuid7()))

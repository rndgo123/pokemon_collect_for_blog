from enum import StrEnum

from pokemon_events.models import EventStatus, PokemonEvent


class ChangeType(StrEnum):
    NEW = "NEW"
    UPDATED = "UPDATED"
    UNCHANGED = "UNCHANGED"
    ENDED = "ENDED"


def detect_change(existing: PokemonEvent | None, incoming: PokemonEvent) -> ChangeType:
    if existing is None:
        return ChangeType.NEW
    if existing.status != EventStatus.ENDED and incoming.status == EventStatus.ENDED:
        return ChangeType.ENDED
    if existing.content_hash == incoming.content_hash and existing.status == incoming.status:
        return ChangeType.UNCHANGED
    return ChangeType.UPDATED

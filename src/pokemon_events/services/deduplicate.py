from pokemon_events.models import PokemonEvent


def deduplicate_events(events: list[PokemonEvent]) -> list[PokemonEvent]:
    unique: dict[str, PokemonEvent] = {}
    for event in events:
        previous = unique.get(event.id)
        if previous and (
            previous.content_hash != event.content_hash or previous.status != event.status
        ):
            raise ValueError(f"conflicting events share id {event.id!r}")
        if previous is None or event.collected_at > previous.collected_at:
            unique[event.id] = event
    return list(unique.values())

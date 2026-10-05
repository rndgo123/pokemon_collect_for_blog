import tomllib
from dataclasses import replace
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from pokemon_events.models import PokemonEvent
from pokemon_events.services.content_hash import hash_content


DEFAULT_ALIASES = Path(__file__).parents[3] / "config" / "pokemon_aliases.toml"


@lru_cache
def load_aliases(path: str | Path = DEFAULT_ALIASES) -> dict[str, tuple[str, ...]]:
    with Path(path).open("rb") as file:
        values = tomllib.load(file).get("pokemon", {})
    if not isinstance(values, dict) or not values:
        raise ValueError("pokemon aliases must be a non-empty table")
    aliases: dict[str, tuple[str, ...]] = {}
    for name, terms in values.items():
        if not isinstance(name, str) or not isinstance(terms, list) or not all(
            isinstance(term, str) and term.strip() for term in terms
        ):
            raise ValueError(f"invalid pokemon aliases for {name!r}")
        aliases[name] = tuple(term.casefold() for term in terms)
    return aliases


def tag_event(
    event: PokemonEvent,
    aliases: dict[str, tuple[str, ...]] | None = None,
) -> PokemonEvent:
    aliases = aliases or load_aliases()
    text = " ".join(value for value in (event.title, event.description) if value).casefold()
    pokemon = [name for name, terms in aliases.items() if any(term in text for term in terms)]
    if pokemon == event.pokemon:
        return event
    tagged = replace(event, pokemon=pokemon)
    return replace(tagged, content_hash=hash_content(_fingerprint(tagged)))


def _fingerprint(event: PokemonEvent) -> dict[str, object]:
    def iso(value: datetime | None) -> str | None:
        return value.isoformat() if value else None

    return {
        "title": event.title,
        "description": event.description,
        "category": event.category.value,
        "pokemon": event.pokemon,
        "country": event.country,
        "region": event.region,
        "venue": event.venue,
        "start_date": iso(event.start_date),
        "end_date": iso(event.end_date),
        "source_url": event.source_url,
        "published_at": iso(event.published_at),
        "status": event.status.value,
        "source_hash": event.source_hash,
        "detail_hash": event.detail_hash,
    }

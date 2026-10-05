from abc import ABC, abstractmethod

from pokemon_events.models import PokemonEvent


class BaseCollector(ABC):
    source_id: str
    source_name: str
    source_url: str

    @abstractmethod
    def collect(self) -> list[PokemonEvent]:
        """Collect and normalize events from one official source."""

    def enrich(
        self, event: PokemonEvent, previous: PokemonEvent | None = None
    ) -> PokemonEvent:
        """Optionally add fields from a detail page."""
        return event

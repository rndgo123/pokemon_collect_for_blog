from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from urllib.parse import urlsplit


class Category(StrEnum):
    POPUP = "POPUP"
    GAME = "GAME"
    POKEMON_GO = "POKEMON_GO"
    GOODS = "GOODS"
    TCG = "TCG"
    TRAVEL = "TRAVEL"
    COLLAB = "COLLAB"
    OTHER = "OTHER"


class EventStatus(StrEnum):
    UPCOMING = "UPCOMING"
    ACTIVE = "ACTIVE"
    ENDED = "ENDED"
    UNKNOWN = "UNKNOWN"


@dataclass(slots=True)
class PokemonEvent:
    id: str
    title: str
    category: Category
    country: str
    source_name: str
    source_url: str
    collected_at: datetime
    content_hash: str
    source_country: str | None = None
    source_hash: str | None = None
    detail_hash: str | None = None
    detail_checked_at: datetime | None = None
    description: str | None = None
    pokemon: list[str] = field(default_factory=list)
    region: str | None = None
    venue: str | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    published_at: datetime | None = None
    status: EventStatus = EventStatus.UNKNOWN

    def __post_init__(self) -> None:
        for name in ("id", "title", "country", "source_name", "source_url", "content_hash"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} must not be empty")
        if len(self.country) != 2 or not self.country.isalpha() or not self.country.isupper():
            raise ValueError("country must be an ISO 3166-1 alpha-2 code")
        if self.source_country is None:
            self.source_country = self.country
        if (
            len(self.source_country) != 2
            or not self.source_country.isalpha()
            or not self.source_country.isupper()
        ):
            raise ValueError("source_country must be an ISO 3166-1 alpha-2 code")
        source_url = urlsplit(self.source_url)
        if source_url.scheme not in {"http", "https"} or not source_url.netloc:
            raise ValueError("source_url must be an absolute HTTP(S) URL")
        for name in (
            "collected_at",
            "detail_checked_at",
            "start_date",
            "end_date",
            "published_at",
        ):
            value = getattr(self, name)
            if value is not None and value.tzinfo is None:
                raise ValueError(f"{name} must be timezone-aware")
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date must not be after end_date")

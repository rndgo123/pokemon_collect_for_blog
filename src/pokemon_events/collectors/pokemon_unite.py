import html
import re
import tomllib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request

from pokemon_events.collectors.base import BaseCollector
from pokemon_events.collectors.http import fetch_bytes
from pokemon_events.models import Category, PokemonEvent
from pokemon_events.services.content_hash import hash_content


DEFAULT_CONFIG = Path(__file__).parents[3] / "config" / "sources.toml"
JST = timezone(timedelta(hours=9))
ITEM_PATTERN = re.compile(
    r'<li class="category_singleli[^>]*>\s*<a href="(?P<url>[^"]+)"[\s\S]*?'
    r'<span class="category_year">(?P<year>\d{4})</span>\s*'
    r'<span class="category_day">(?P<day>\d{2}/\d{2})</span>[\s\S]*?'
    r'<li class="category_nameli">(?P<label>[\s\S]*?)</li>[\s\S]*?'
    r'<h3 class="category_txt">(?P<title>[\s\S]*?)</h3>',
    re.IGNORECASE,
)


class PokemonUniteCollector(BaseCollector):
    source_id = "pokemon_unite_jp"
    source_name = "Pokémon UNITE Japan"

    def __init__(self, config_path: str | Path = DEFAULT_CONFIG) -> None:
        with Path(config_path).open("rb") as file:
            config = tomllib.load(file)["sources"][self.source_id]
        self.source_name = config["name"]
        self.list_url = config["list_url"]
        self.source_url = self.list_url
        self.country = config["country"]
        self.timeout = float(config["timeout_seconds"])
        self.user_agent = config["user_agent"]
        if self.timeout <= 0:
            raise ValueError("timeout_seconds must be positive")

    def collect(self) -> list[PokemonEvent]:
        request = Request(self.list_url, headers={"User-Agent": self.user_agent})
        markup = fetch_bytes(request, self.timeout, 2.0).decode("utf-8")
        collected_at = datetime.now(timezone.utc)
        events: list[PokemonEvent] = []
        for match in ITEM_PATTERN.finditer(markup):
            source_url = html.unescape(match["url"])
            title = _text(match["title"])
            published_at = datetime.strptime(
                f'{match["year"]}/{match["day"]}', "%Y/%m/%d"
            ).replace(tzinfo=JST)
            slug = urlsplit(source_url).path.strip("/").split("topics/", 1)[-1].replace("/", ":")
            content_hash = hash_content(
                {
                    "title": title,
                    "source_url": source_url,
                    "published_at": published_at.isoformat(),
                }
            )
            events.append(
                PokemonEvent(
                    id=f"{self.source_id}:{slug}",
                    title=title,
                    category=Category.GAME,
                    country=self.country,
                    source_name=self.source_name,
                    source_url=source_url,
                    published_at=published_at,
                    collected_at=collected_at,
                    content_hash=content_hash,
                )
            )
        if not events:
            raise ValueError("pokemonunite.jp response contained no topic items")
        return events


def _text(markup: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", markup)).split())

import json
import html
import re
import time
import tomllib
from dataclasses import replace
from datetime import datetime, time as datetime_time, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from urllib.request import Request

from pokemon_events.collectors.base import BaseCollector
from pokemon_events.collectors.http import fetch_bytes
from pokemon_events.models import Category, EventStatus, PokemonEvent
from pokemon_events.services.content_hash import hash_content


DEFAULT_CONFIG = Path(__file__).parents[3] / "config" / "sources.toml"
CATEGORY_BY_TERM = {"game": Category.GAME, "card": Category.TCG, "shop": Category.GOODS}
JST = timezone(timedelta(hours=9))
SCRIPT_PATTERN = re.compile(r"<script\b[\s\S]*?</script>", re.IGNORECASE)
ROW_PATTERN = re.compile(
    r"<tr\b[^>]*>[\s\S]*?<th\b[^>]*>(?P<label>[\s\S]*?)</th>"
    r"[\s\S]*?<td\b[^>]*>(?P<value>[\s\S]*?)</td>[\s\S]*?</tr>",
    re.IGNORECASE,
)
DATE_RANGE_PATTERN = re.compile(
    r"(?:(?P<start_year>\d{4})年)?(?P<start_month>\d{1,2})月(?P<start_day>\d{1,2})日"
    r"[^～~]{0,20}[～~]\s*(?:(?P<end_year>\d{4})年)?"
    r"(?:(?P<end_month>\d{1,2})月)?(?P<end_day>\d{1,2})日"
)
DATE_LABELS = ("開催期間", "実施期間", "開催日時", "実施日時", "開催日")
VENUE_LABELS = ("開催場所", "実施場所")


class PokemonJapanCollector(BaseCollector):
    source_id = "pokemon_japan"
    source_name = "Pokémon Japan"

    def __init__(self, config_path: str | Path = DEFAULT_CONFIG, max_pages: int | None = None) -> None:
        with Path(config_path).open("rb") as file:
            config = tomllib.load(file)["sources"][self.source_id]
        self.source_name = config["name"]
        self.source_url = config["list_url"]
        self.api_url = config["api_url"]
        self.country = config["country"]
        self.event_flag = int(config["event_flag"])
        self.page_size = int(config["page_size"])
        self.delay = float(config["request_delay_seconds"])
        self.timeout = float(config["timeout_seconds"])
        self.user_agent = config["user_agent"]
        self.detail_lookback_days = int(config.get("detail_lookback_days", 30))
        self.detail_refresh_hours = int(config.get("detail_refresh_hours", 24))
        self.max_pages = max_pages
        if self.page_size < 1 or self.timeout <= 0 or self.delay < 0:
            raise ValueError("invalid collector timing or page size configuration")
        if max_pages is not None and max_pages < 1:
            raise ValueError("max_pages must be positive")
        if self.detail_lookback_days < 0 or self.detail_refresh_hours < 0:
            raise ValueError("detail timing must not be negative")

    def collect(self) -> list[PokemonEvent]:
        collected_at = datetime.now(timezone.utc)
        events: list[PokemonEvent] = []
        page = 1
        while True:
            payload = self._get_page(page)
            results = payload.get("results")
            paging = payload.get("paging")
            if not isinstance(results, list) or not isinstance(paging, dict):
                raise ValueError("unexpected pokemon.co.jp API response")
            events.extend(self._normalize(item, collected_at) for item in results)
            if not paging.get("nextPage") or (self.max_pages and page >= self.max_pages):
                return events
            page += 1
            time.sleep(self.delay)

    def _get_page(self, page: int) -> dict:
        query = urlencode(
            [("limit", self.page_size), ("page", page), ("flg[]", self.event_flag)]
        )
        request = Request(
            f"{self.api_url}?{query}",
            headers={"Accept": "application/json", "User-Agent": self.user_agent},
        )
        payload = json.loads(fetch_bytes(request, self.timeout, self.delay))
        if not isinstance(payload, dict):
            raise ValueError("pokemon.co.jp API returned a non-object JSON value")
        return payload

    def enrich(
        self, event: PokemonEvent, previous: PokemonEvent | None = None
    ) -> PokemonEvent:
        now = datetime.now(timezone.utc)
        if not _should_refresh(
            event,
            previous,
            now,
            self.detail_lookback_days,
            self.detail_refresh_hours,
        ):
            return (
                _with_details(
                    event,
                    previous.start_date,
                    previous.end_date,
                    previous.venue,
                    previous.detail_hash,
                    previous.detail_checked_at,
                )
                if previous
                else event
            )
        request = Request(event.source_url, headers={"User-Agent": self.user_agent})
        markup = fetch_bytes(request, self.timeout, self.delay).decode("utf-8")
        time.sleep(self.delay)
        start_date, end_date, venue, detail_hash = _detail_fields(
            markup, event.published_at.year
        )
        return _with_details(event, start_date, end_date, venue, detail_hash, now)

    def _normalize(self, item: object, collected_at: datetime) -> PokemonEvent:
        if not isinstance(item, dict):
            raise ValueError("pokemon.co.jp result must be an object")
        try:
            item_id = int(item["id"])
            title = item["title"].strip()
            source_url = item["full_uniq"].strip()
            published_at = datetime.strptime(item["start_date"], "%Y.%m.%d").replace(tzinfo=JST)
        except (KeyError, AttributeError, TypeError, ValueError) as error:
            raise ValueError(f"invalid pokemon.co.jp result: {item!r}") from error
        description = item.get("txt_1")
        description = description.strip() if isinstance(description, str) and description.strip() else None
        category = CATEGORY_BY_TERM.get(item.get("term"), Category.OTHER)
        content = {
            "title": title,
            "description": description,
            "category": category.value,
            "source_url": source_url,
            "published_at": published_at.isoformat(),
        }
        content_hash = hash_content(content)
        return PokemonEvent(
            id=f"{self.source_id}:{item_id}",
            title=title,
            description=description,
            category=category,
            country=self.country,
            source_name=self.source_name,
            source_url=source_url,
            published_at=published_at,
            collected_at=collected_at,
            content_hash=content_hash,
            source_hash=content_hash,
        )


def _detail_fields(
    markup: str, default_year: int
) -> tuple[datetime | None, datetime | None, str | None, str]:
    visible_markup = SCRIPT_PATTERN.sub("", markup)
    rows = [
        (_text(match["label"]), _text(match["value"]))
        for match in ROW_PATTERN.finditer(visible_markup)
    ]
    date_values = [value for label, value in rows if label.endswith(DATE_LABELS)]
    ranges = DATE_RANGE_PATTERN.findall(date_values[0]) if len(date_values) == 1 else []
    start_date = end_date = None
    if len(ranges) == 1:
        match = DATE_RANGE_PATTERN.search(date_values[0])
        assert match is not None
        start_year = int(match["start_year"] or default_year)
        start_month = int(match["start_month"])
        end_month = int(match["end_month"] or start_month)
        end_year = int(match["end_year"] or start_year + (end_month < start_month))
        start_date = datetime(
            start_year, start_month, int(match["start_day"]), tzinfo=JST
        )
        end_date = datetime.combine(
            datetime(end_year, end_month, int(match["end_day"])).date(),
            datetime_time.max,
            JST,
        )
    venues = {value for label, value in rows if label.endswith(VENUE_LABELS) and value}
    relevant_rows = [
        (label, value)
        for label, value in rows
        if label.endswith(DATE_LABELS + VENUE_LABELS)
    ]
    return (
        start_date,
        end_date,
        venues.pop() if len(venues) == 1 else None,
        hash_content({"rows": relevant_rows}),
    )


def _with_details(
    event: PokemonEvent,
    start_date: datetime | None,
    end_date: datetime | None,
    venue: str | None,
    detail_hash: str | None,
    detail_checked_at: datetime | None,
) -> PokemonEvent:
    if not any((start_date, end_date, venue, detail_hash, detail_checked_at)):
        return event
    today = datetime.now(JST).date()
    status = EventStatus.UNKNOWN
    if start_date and end_date:
        status = (
            EventStatus.UPCOMING
            if today < start_date.date()
            else EventStatus.ENDED
            if today > end_date.date()
            else EventStatus.ACTIVE
        )
    enriched = replace(
        event,
        country=_event_country(venue, event.country),
        start_date=start_date,
        end_date=end_date,
        venue=venue,
        status=status,
        detail_hash=detail_hash,
        detail_checked_at=detail_checked_at,
    )
    return replace(
        enriched,
        content_hash=hash_content(
            {
                "title": enriched.title,
                "description": enriched.description,
                "category": enriched.category.value,
                "country": enriched.country,
                "source_country": enriched.source_country,
                "source_hash": enriched.source_hash,
                "detail_hash": detail_hash,
                "source_url": enriched.source_url,
                "published_at": enriched.published_at.isoformat()
                if enriched.published_at
                else None,
                "start_date": start_date.isoformat() if start_date else None,
                "end_date": end_date.isoformat() if end_date else None,
                "venue": venue,
                "status": status.value,
            }
        ),
    )


def _text(markup: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", markup)).split())


def _is_official_detail(url: str) -> bool:
    parts = urlsplit(url)
    return parts.hostname == "www.pokemon.co.jp" and parts.path.startswith("/info/")


def _event_country(venue: str | None, default: str) -> str:
    # ponytail: expand this map only when a new verified overseas venue appears.
    return "US" if venue and "アメリカ" in venue else default


def _should_refresh(
    event: PokemonEvent,
    previous: PokemonEvent | None,
    now: datetime,
    lookback_days: int,
    refresh_hours: int,
) -> bool:
    if event.published_at is None or not _is_official_detail(event.source_url):
        return False
    recent = now - event.published_at <= timedelta(days=lookback_days)
    if previous is None:
        return recent
    if previous.source_hash != event.source_hash:
        return True
    tracked = recent or previous.status in {EventStatus.UPCOMING, EventStatus.ACTIVE}
    return tracked and (
        previous.detail_checked_at is None
        or now - previous.detail_checked_at >= timedelta(hours=refresh_hours)
    )

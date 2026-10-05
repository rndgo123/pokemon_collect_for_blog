import html
import re
import time
import tomllib
from dataclasses import replace
from datetime import datetime, time as datetime_time, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import Request

from pokemon_events.collectors.base import BaseCollector
from pokemon_events.collectors.http import fetch_bytes
from pokemon_events.models import Category, EventStatus, PokemonEvent
from pokemon_events.services.content_hash import hash_content


DEFAULT_CONFIG = Path(__file__).parents[3] / "config" / "sources.toml"
KST = timezone(timedelta(hours=9))
ITEM_PATTERN = re.compile(
    r'<li class="col-lg-3[^>]*>\s*<a href="(?P<url>[^"]+)"[\s\S]*?'
    r"<h3>(?P<title>[\s\S]*?)</h3>[\s\S]*?"
    r'<ul class="list-split">\s*<li>(?P<category>[\s\S]*?)</li>\s*'
    r"<li>(?P<date>[\s\S]*?)</li>",
    re.IGNORECASE,
)
CATEGORY_MAP = {"카드 게임": Category.TCG, "게임": Category.GAME, "상품": Category.GOODS}
BODY_PATTERN = re.compile(
    r'<div class="bx-board">(?P<body>[\s\S]*?)(?=<div class="bx-btm">)',
    re.IGNORECASE,
)
SHARE_PATTERN = re.compile(r'<ul class="lst-connect">[\s\S]*?</ul>', re.IGNORECASE)
IMAGE_PATTERN = re.compile(r'<img\b[^>]*\bsrc="([^"]+)"', re.IGNORECASE)
DATE_PATTERN = re.compile(
    r"(?:(?P<start_year>\d{4})\s*년\s*)?(?P<start_month>\d{1,2})\s*월\s*"
    r"(?P<start_day>\d{1,2})\s*일[^~～]{0,20}[~～]\s*"
    r"(?:(?P<end_year>\d{4})\s*년\s*)?(?:(?P<end_month>\d{1,2})\s*월\s*)?"
    r"(?P<end_day>\d{1,2})\s*일"
)


class PokemonKoreaCollector(BaseCollector):
    source_id = "pokemon_korea"
    source_name = "Pokémon Korea"

    def __init__(self, config_path: str | Path = DEFAULT_CONFIG, max_pages: int | None = None) -> None:
        with Path(config_path).open("rb") as file:
            config = tomllib.load(file)["sources"][self.source_id]
        self.source_name = config["name"]
        self.list_url = config["list_url"]
        self.source_url = self.list_url
        self.endpoint = config["endpoint"]
        self.country = config["country"]
        self.delay = float(config["request_delay_seconds"])
        self.timeout = float(config["timeout_seconds"])
        self.user_agent = config["user_agent"]
        self.detail_lookback_days = int(config.get("detail_lookback_days", 30))
        self.detail_refresh_hours = int(config.get("detail_refresh_hours", 24))
        self.max_pages = max_pages
        if (
            self.timeout <= 0
            or self.delay < 0
            or self.detail_lookback_days < 0
            or self.detail_refresh_hours < 0
            or (max_pages is not None and max_pages < 1)
        ):
            raise ValueError("invalid collector timing or page limit configuration")

    def collect(self) -> list[PokemonEvent]:
        collected_at = datetime.now(timezone.utc)
        events: list[PokemonEvent] = []
        page = 1
        while True:
            body = urlencode(
                {"pn": page, "cate": 0, "sword": "", "rcode": "menu_news"}
            ).encode()
            request = Request(
                self.endpoint,
                data=body,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": self.user_agent,
                },
            )
            parts = fetch_bytes(request, self.timeout, self.delay).decode("utf-8").split("#|#")
            if len(parts) < 3 or not parts[2].strip().isdigit():
                raise ValueError("unexpected pokemonkorea.co.kr AJAX response")
            events.extend(self._parse(parts[1], collected_at))
            total_pages = int(parts[2].strip())
            if page >= total_pages or (self.max_pages and page >= self.max_pages):
                return events
            page += 1
            time.sleep(self.delay)

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
                _with_detail(
                    event,
                    previous.description,
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
        description, start_date, end_date, venue, detail_hash = _detail_fields(
            markup, event.published_at.year
        )
        return _with_detail(
            event, description, start_date, end_date, venue, detail_hash, now
        )

    def _parse(self, markup: str, collected_at: datetime) -> list[PokemonEvent]:
        events: list[PokemonEvent] = []
        for match in ITEM_PATTERN.finditer(markup):
            title = _text(match["title"])
            label = _text(match["category"])
            published_at = datetime.strptime(_text(match["date"]), "%Y년 %m월 %d일").replace(
                tzinfo=KST
            )
            source_url = _canonical_url(urljoin(self.list_url, html.unescape(match["url"])))
            path_id = re.search(r"/news/\d+/(\d+)", urlsplit(source_url).path)
            event_id = (
                path_id.group(1)
                if path_id
                else hash_content(
                    {
                        "url": source_url,
                        "title": title,
                        "published_at": published_at.isoformat(),
                    }
                )[:16]
            )
            category = CATEGORY_MAP.get(label, Category.OTHER)
            content_hash = hash_content(
                {
                    "title": title,
                    "category": category.value,
                    "source_url": source_url,
                    "published_at": published_at.isoformat(),
                }
            )
            events.append(
                PokemonEvent(
                    id=f"{self.source_id}:{event_id}",
                    title=title,
                    category=category,
                    country=self.country,
                    source_name=self.source_name,
                    source_url=source_url,
                    published_at=published_at,
                    collected_at=collected_at,
                    content_hash=content_hash,
                    source_hash=content_hash,
                )
            )
        if not events:
            raise ValueError("pokemonkorea.co.kr response contained no news items")
        return events


def _text(markup: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", markup)).split())


def _canonical_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _detail_fields(
    markup: str, default_year: int
) -> tuple[str | None, datetime | None, datetime | None, str | None, str]:
    match = BODY_PATTERN.search(markup)
    if not match:
        raise ValueError("pokemonkorea.co.kr detail body was not found")
    body = SHARE_PATTERN.sub("", match["body"])
    images = sorted({_canonical_url(urljoin("https://www.pokemonkorea.co.kr", url)) for url in IMAGE_PATTERN.findall(body)})
    text = _lines(body)
    description = text.replace("\n", " ")[:300] or None
    date_lines = [line for line in text.splitlines() if re.search(r"(?:개최|행사|이벤트|운영)\s*기간\s*[:：]", line)]
    ranges = DATE_PATTERN.findall(date_lines[0]) if len(date_lines) == 1 else []
    start_date = end_date = None
    if len(ranges) == 1:
        date_match = DATE_PATTERN.search(date_lines[0])
        assert date_match is not None
        start_year = int(date_match["start_year"] or default_year)
        start_month = int(date_match["start_month"])
        end_month = int(date_match["end_month"] or start_month)
        end_year = int(date_match["end_year"] or start_year + (end_month < start_month))
        start_date = datetime(start_year, start_month, int(date_match["start_day"]), tzinfo=KST)
        end_date = datetime.combine(
            datetime(end_year, end_month, int(date_match["end_day"])).date(),
            datetime_time.max,
            KST,
        )
    venue_lines = [
        re.split(r"[:：]", line, maxsplit=1)[1].strip(" ・")
        for line in text.splitlines()
        if re.search(r"(?:개최|행사|이벤트)\s*장소\s*[:：]", line)
    ]
    venue = venue_lines[0] if len(set(venue_lines)) == 1 and venue_lines else None
    return description, start_date, end_date, venue, hash_content({"text": text, "images": images})


def _lines(markup: str) -> str:
    markup = re.sub(r"<(?:br\s*/?|/p|/div|/li)>", "\n", markup, flags=re.IGNORECASE)
    return "\n".join(
        line for line in (_text(line) for line in markup.splitlines()) if line
    )


def _with_detail(
    event: PokemonEvent,
    description: str | None,
    start_date: datetime | None,
    end_date: datetime | None,
    venue: str | None,
    detail_hash: str | None,
    detail_checked_at: datetime | None,
) -> PokemonEvent:
    if not any((description, start_date, end_date, venue, detail_hash, detail_checked_at)):
        return event
    today = datetime.now(KST).date()
    status = EventStatus.UNKNOWN
    if start_date and end_date:
        status = EventStatus.UPCOMING if today < start_date.date() else EventStatus.ENDED if today > end_date.date() else EventStatus.ACTIVE
    enriched = replace(
        event,
        description=description,
        country="US" if venue and "미국" in venue else event.country,
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
                "source_hash": enriched.source_hash,
                "detail_hash": detail_hash,
                "description": description,
                "country": enriched.country,
                "start_date": start_date.isoformat() if start_date else None,
                "end_date": end_date.isoformat() if end_date else None,
                "venue": venue,
                "status": status.value,
            }
        ),
    )


def _should_refresh(
    event: PokemonEvent,
    previous: PokemonEvent | None,
    now: datetime,
    lookback_days: int,
    refresh_hours: int,
) -> bool:
    if event.published_at is None or not _is_internal_detail(event.source_url):
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


def _is_internal_detail(url: str) -> bool:
    parts = urlsplit(url)
    return parts.hostname in {"pokemonkorea.co.kr", "www.pokemonkorea.co.kr"} and bool(
        re.fullmatch(r"/news/\d+/\d+", parts.path)
    )

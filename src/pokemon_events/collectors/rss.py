from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from math import isfinite
from urllib.parse import urljoin, urlsplit
from urllib.request import Request
from xml.etree import ElementTree as ET

from pokemon_events.collectors.base import BaseCollector
from pokemon_events.collectors.http import fetch_bytes
from pokemon_events.models import Category, PokemonEvent
from pokemon_events.services.content_hash import hash_content


ATOM = "{http://www.w3.org/2005/Atom}"
XML_BASE = "{http://www.w3.org/XML/1998/namespace}base"


class _FeedTreeBuilder(ET.TreeBuilder):
    def doctype(self, name: str, pubid: str | None, system: str | None) -> None:
        raise ValueError("DTD and entity declarations are not accepted in feeds")


class RssCollector(BaseCollector):
    """Approved RSS 2.0 / Atom metadata only; never fetch article bodies or images."""

    def __init__(self, source_id: str, config: dict) -> None:
        if config.get("enabled") is not True or config.get("policy_approved") is not True:
            raise ValueError("RSS source requires enabled=true and policy_approved=true")
        self.source_id = source_id
        self.source_name = config["name"]
        self.source_url = _http_url(config["feed_url"])
        _http_url(config["policy_url"])
        self.country = config["country"]
        self.category = Category(config.get("category", "OTHER"))
        self.timeout = float(config.get("timeout_seconds", 20))
        self.delay = float(config.get("request_delay_seconds", 2))
        self.user_agent = config.get("user_agent", "PokemonEventPipeline/0.1 (personal-use)")
        if not source_id.strip() or not self.source_name.strip():
            raise ValueError("source id and name must not be empty")
        if len(self.country) != 2 or not self.country.isalpha() or not self.country.isupper():
            raise ValueError("country must be an ISO alpha-2 code")
        if not isfinite(self.timeout) or not isfinite(self.delay) or self.timeout <= 0 or self.delay < 0:
            raise ValueError("invalid RSS request timing")

    def collect(self) -> list[PokemonEvent]:
        request = Request(self.source_url, headers={
            "User-Agent": self.user_agent,
            "Accept": "application/rss+xml, application/atom+xml, application/xml",
        })
        payload = fetch_bytes(request, self.timeout, self.delay, max_bytes=2 * 1024 * 1024)
        return self.parse(payload)

    def parse(self, payload: bytes) -> list[PokemonEvent]:
        if len(payload) > 2 * 1024 * 1024:
            raise ValueError("feed exceeds 2 MiB")
        root = ET.fromstring(payload, parser=ET.XMLParser(target=_FeedTreeBuilder()))
        if root.tag == "rss" and root.get("version") == "2.0" and root.find("channel") is not None:
            entries = root.findall("channel/item")
            atom = False
        elif root.tag == ATOM + "feed":
            entries = root.findall(ATOM + "entry")
            atom = True
        else:
            raise ValueError("expected RSS 2.0 or Atom, not HTML or another XML format")
        # ponytail: empty feeds fail closed; add source-specific empty-feed approval when needed.
        if not entries:
            raise ValueError("empty feed: inspect source before accepting a successful run")
        now = datetime.now(timezone.utc)
        events = []
        base_url = urljoin(self.source_url, root.get(XML_BASE, ""))
        for entry in entries:
            title = _text(entry.find(ATOM + "title" if atom else "title"))
            if atom:
                links = [link for link in entry.findall(ATOM + "link")
                         if link.get("rel", "alternate") == "alternate"
                         and link.get("type", "text/html") in {"text/html", "application/xhtml+xml"}]
                if not links or not links[0].get("href"):
                    raise ValueError("Atom entry has no article link")
                base = urljoin(base_url, entry.get(XML_BASE, ""))
                base = urljoin(base, links[0].get(XML_BASE, ""))
                url = urljoin(base, links[0].get("href"))
                identity = _text(entry.find(ATOM + "id"))
                date_text = _text(entry.find(ATOM + "published"))
                if not date_text:
                    date_text = _text(entry.find(ATOM + "updated"))
            else:
                url = urljoin(base_url, _text(entry.find("link")))
                identity = _text(entry.find("guid"))
                date_text = _text(entry.find("pubDate"))
                if entry.find("link") is None or not _text(entry.find("link")):
                    raise ValueError("RSS item has no article link")
            url = _http_url(url)
            if not title:
                raise ValueError("feed entry title must not be empty")
            published = _date(date_text, atom) if date_text else None
            fingerprint = hash_content({
                "title": title, "source_url": url, "category": self.category.value,
                "published_at": published.isoformat() if published else None,
            })
            events.append(PokemonEvent(
                id=f"{self.source_id}:{hash_content({'key': identity or url})}",
                title=title, category=self.category, country=self.country,
                source_name=self.source_name, source_url=url, collected_at=now,
                published_at=published, content_hash=fingerprint, source_hash=fingerprint,
            ))
        return events


def _text(element: ET.Element | None) -> str:
    return " ".join("".join(element.itertext()).split()) if element is not None else ""


def _http_url(value: str) -> str:
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
        raise ValueError("expected an absolute HTTP(S) URL without credentials")
    return value


def _date(value: str, atom: bool) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00")) if atom else parsedate_to_datetime(value)
    if parsed.tzinfo is None:
        raise ValueError("feed date must include a timezone")
    return parsed.astimezone(timezone.utc)

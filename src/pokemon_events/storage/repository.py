import json
import sqlite3
from datetime import datetime
from pathlib import Path

from pokemon_events.models import Category, EventStatus, PokemonEvent
from pokemon_events.services.change_detector import ChangeType, detect_change


SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    base_url TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    last_collected_at TEXT
);

CREATE TABLE IF NOT EXISTS collection_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL REFERENCES sources(id),
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL DEFAULT 'RUNNING',
    items_seen INTEGER NOT NULL DEFAULT 0,
    error TEXT
);

CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    category TEXT NOT NULL,
    pokemon TEXT NOT NULL DEFAULT '[]',
    country TEXT NOT NULL,
    source_country TEXT NOT NULL,
    region TEXT,
    venue TEXT,
    start_date TEXT,
    end_date TEXT,
    source_name TEXT NOT NULL,
    source_url TEXT NOT NULL,
    published_at TEXT,
    collected_at TEXT NOT NULL,
    status TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    source_hash TEXT,
    detail_hash TEXT,
    detail_checked_at TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS event_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    change_type TEXT NOT NULL,
    changed_at TEXT NOT NULL,
    snapshot TEXT NOT NULL
);
"""
MATERIAL_FIELDS = (
    "title",
    "description",
    "category",
    "country",
    "region",
    "venue",
    "start_date",
    "end_date",
    "source_url",
    "published_at",
    "status",
)


class SQLiteRepository:
    def __init__(self, path: str | Path) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.executescript(SCHEMA)
        columns = {
            row[1] for row in self.connection.execute("PRAGMA table_info(events)")
        }
        for name in ("source_country", "source_hash", "detail_hash", "detail_checked_at"):
            if name not in columns:
                self.connection.execute(f"ALTER TABLE events ADD COLUMN {name} TEXT")
        self.connection.execute(
            "UPDATE events SET source_country = country WHERE source_country IS NULL"
        )
        self.connection.execute(
            "UPDATE events SET source_hash = content_hash WHERE source_hash IS NULL"
        )
        self.connection.execute(
            """UPDATE events SET content_hash = source_hash
               WHERE detail_hash IS NULL AND detail_checked_at IS NULL
                 AND start_date IS NULL AND end_date IS NULL AND venue IS NULL"""
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "SQLiteRepository":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def save_source(self, source_id: str, name: str, base_url: str, enabled: bool = True) -> None:
        self.connection.execute(
            """INSERT INTO sources (id, name, base_url, enabled) VALUES (?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET name=excluded.name,
                   base_url=excluded.base_url, enabled=excluded.enabled""",
            (source_id, name, base_url, enabled),
        )
        self.connection.commit()

    def save_event(self, event: PokemonEvent) -> ChangeType:
        with self.connection:
            row = self.connection.execute(
                "SELECT * FROM events WHERE id = ?", (event.id,)
            ).fetchone()
            change = detect_change(_event_from_row(row) if row else None, event)
            record = _event_record(event)
            if change == ChangeType.NEW:
                self.connection.execute(
                    """INSERT INTO events (
                           id, title, description, category, pokemon, country, source_country,
                           region, venue,
                           start_date, end_date, source_name, source_url, published_at,
                           collected_at, status, content_hash, source_hash, detail_hash,
                           detail_checked_at, first_seen_at, last_seen_at
                       ) VALUES (
                           :id, :title, :description, :category, :pokemon, :country,
                           :source_country, :region, :venue, :start_date, :end_date,
                           :source_name, :source_url,
                           :published_at, :collected_at, :status, :content_hash,
                           :source_hash, :detail_hash, :detail_checked_at,
                           :collected_at, :collected_at
                       )""",
                    record,
                )
            elif change == ChangeType.UNCHANGED:
                self.connection.execute(
                    """UPDATE events SET collected_at=:collected_at,
                           source_hash=:source_hash, detail_hash=:detail_hash,
                           detail_checked_at=:detail_checked_at,
                           last_seen_at=:collected_at WHERE id=:id""",
                    record,
                )
            else:
                self.connection.execute(
                    """UPDATE events SET title=:title, description=:description,
                           category=:category, pokemon=:pokemon, country=:country,
                           source_country=:source_country,
                           region=:region, venue=:venue, start_date=:start_date,
                           end_date=:end_date, source_name=:source_name,
                           source_url=:source_url, published_at=:published_at,
                           collected_at=:collected_at, status=:status,
                           content_hash=:content_hash, source_hash=:source_hash,
                           detail_hash=:detail_hash, detail_checked_at=:detail_checked_at,
                           last_seen_at=:collected_at
                       WHERE id=:id""",
                    record,
                )
            if change != ChangeType.UNCHANGED:
                self.connection.execute(
                    """INSERT INTO event_history (event_id, change_type, changed_at, snapshot)
                       VALUES (?, ?, ?, ?)""",
                    (
                        event.id,
                        change.value,
                        _iso(event.collected_at),
                        json.dumps(_event_snapshot(event), ensure_ascii=False, sort_keys=True),
                    ),
                )
        return change

    def start_run(self, source_id: str, started_at: datetime) -> int:
        if started_at.tzinfo is None:
            raise ValueError("started_at must be timezone-aware")
        cursor = self.connection.execute(
            "INSERT INTO collection_runs (source_id, started_at) VALUES (?, ?)",
            (source_id, _iso(started_at)),
        )
        self.connection.commit()
        return cursor.lastrowid

    def finish_run(
        self,
        run_id: int,
        finished_at: datetime,
        status: str,
        items_seen: int,
        error: str | None = None,
    ) -> None:
        if finished_at.tzinfo is None:
            raise ValueError("finished_at must be timezone-aware")
        if status not in {"SUCCESS", "FAILED"} or items_seen < 0:
            raise ValueError("invalid collection run result")
        self.connection.execute(
            """UPDATE collection_runs SET finished_at=?, status=?, items_seen=?, error=?
               WHERE id=?""",
            (_iso(finished_at), status, items_seen, error, run_id),
        )
        self.connection.commit()

    def get_recent_changes(self, since: datetime) -> dict[str, set[str]]:
        return {event_id: details["types"] for event_id, details in self.get_recent_change_details(since).items()}

    def get_recent_change_details(self, since: datetime) -> dict[str, dict[str, set[str]]]:
        if since.tzinfo is None:
            raise ValueError("since must be timezone-aware")
        # ponytail: a full history scan is fine for a personal DB; index/materialize if it grows.
        rows = self.connection.execute(
            "SELECT event_id, change_type, changed_at, snapshot FROM event_history ORDER BY id"
        ).fetchall()
        previous: dict[str, dict[str, object]] = {}
        changes: dict[str, dict[str, set[str]]] = {}
        for row in rows:
            snapshot = json.loads(row["snapshot"])
            material = {name: snapshot.get(name) for name in MATERIAL_FIELDS}
            is_material = (
                row["change_type"] != "UPDATED"
                or previous.get(row["event_id"]) != material
            )
            if datetime.fromisoformat(row["changed_at"]) >= since and is_material:
                details = changes.setdefault(row["event_id"], {"types": set(), "fields": set()})
                details["types"].add(row["change_type"])
                if row["event_id"] in previous:
                    details["fields"].update(
                        name for name in MATERIAL_FIELDS
                        if previous[row["event_id"]].get(name) != material.get(name)
                    )
            previous[row["event_id"]] = material
        return changes

    def get_event(self, event_id: str) -> PokemonEvent | None:
        row = self.connection.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
        return _event_from_row(row) if row else None

    def list_events(self) -> list[PokemonEvent]:
        rows = self.connection.execute("SELECT * FROM events ORDER BY collected_at DESC").fetchall()
        return [_event_from_row(row) for row in rows]


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _event_from_row(row: sqlite3.Row) -> PokemonEvent:
    return PokemonEvent(
        id=row["id"],
        title=row["title"],
        description=row["description"],
        category=Category(row["category"]),
        pokemon=json.loads(row["pokemon"]),
        country=row["country"],
        source_country=row["source_country"],
        region=row["region"],
        venue=row["venue"],
        start_date=_datetime(row["start_date"]),
        end_date=_datetime(row["end_date"]),
        source_name=row["source_name"],
        source_url=row["source_url"],
        published_at=_datetime(row["published_at"]),
        collected_at=_datetime(row["collected_at"]),
        status=EventStatus(row["status"]),
        content_hash=row["content_hash"],
        source_hash=row["source_hash"],
        detail_hash=row["detail_hash"],
        detail_checked_at=_datetime(row["detail_checked_at"]),
    )


def _event_record(event: PokemonEvent) -> dict[str, object]:
    return {
        "id": event.id,
        "title": event.title,
        "description": event.description,
        "category": event.category.value,
        "pokemon": json.dumps(event.pokemon, ensure_ascii=False),
        "country": event.country,
        "source_country": event.source_country,
        "region": event.region,
        "venue": event.venue,
        "start_date": _iso(event.start_date),
        "end_date": _iso(event.end_date),
        "source_name": event.source_name,
        "source_url": event.source_url,
        "published_at": _iso(event.published_at),
        "collected_at": _iso(event.collected_at),
        "status": event.status.value,
        "content_hash": event.content_hash,
        "source_hash": event.source_hash,
        "detail_hash": event.detail_hash,
        "detail_checked_at": _iso(event.detail_checked_at),
    }


def _event_snapshot(event: PokemonEvent) -> dict[str, object]:
    snapshot = _event_record(event)
    snapshot["pokemon"] = event.pokemon
    return snapshot

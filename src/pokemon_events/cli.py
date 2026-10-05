import argparse
import sys
import tomllib
from collections import Counter
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from pokemon_events.collectors import (
    PokemonJapanCollector,
    PokemonKoreaCollector,
    PokemonUniteCollector,
)
from pokemon_events.models import Category, EventStatus, PokemonEvent
from pokemon_events.collectors.pokemon_japan import DEFAULT_CONFIG
from pokemon_events.collectors.rss import RssCollector
from pokemon_events.services.curation import FIELD_LABELS, select_candidates
from pokemon_events.services import (
    deduplicate_events,
    detect_change,
    render_blog_draft,
    tag_event,
)
from pokemon_events.storage import SQLiteRepository


COLLECTORS = {
    "pokemon_japan": PokemonJapanCollector,
    "pokemon_korea": PokemonKoreaCollector,
    "pokemon_unite_jp": PokemonUniteCollector,
}
KST = timezone(timedelta(hours=9))


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    with SQLiteRepository(args.db) as repository:
        if args.command == "collect":
            return _collect(repository, args.source, args.config)
        if args.command == "preview":
            return _preview(repository)
        if args.command == "tag":
            return _tag(repository)
        if args.command == "draft":
            return _draft(repository, args.id, args.notes, args.output)
        if args.command == "digest":
            return _digest(repository, args)
        return _show_events(repository, args)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Pokémon official event data pipeline")
    parser.add_argument("--db", default="data/pokemon_events.db", help="SQLite database path")
    commands = parser.add_subparsers(dest="command", required=True)

    collect = commands.add_parser("collect", help="collect official event sources")
    collect.add_argument("--source", help="source id in the TOML configuration")
    collect.add_argument("--config", type=Path, default=DEFAULT_CONFIG)

    commands.add_parser("preview", help="trace the latest Pokémon Japan item without saving")
    commands.add_parser("tag", help="backfill Pokémon tags without collecting")

    draft = commands.add_parser("draft", help="render a factual blog draft")
    draft.add_argument("--id", required=True, help="event id shown by the events command")
    draft.add_argument("--notes", type=Path, help="reviewed editorial TOML notes")
    draft.add_argument("--output", type=Path, help="create a new Markdown file; never overwrite")

    digest = commands.add_parser("digest", help="show actionable blog candidates")
    digest.add_argument("--days", type=_positive_int, default=7)
    digest.add_argument("--ending-days", type=_positive_int, default=7)
    digest.add_argument("--source-country", type=str.upper)
    digest.add_argument("--limit", type=_positive_int, default=20)
    digest.add_argument("--focus", choices=["goods", "all"], default="goods")

    events = commands.add_parser("events", help="show blog post candidates")
    events.add_argument("--active", action="store_true")
    events.add_argument("--new", action="store_true")
    events.add_argument("--updated", action="store_true")
    events.add_argument("--ended", action="store_true")
    events.add_argument("--ending-soon", action="store_true")
    events.add_argument("--starts-this-week", action="store_true")
    events.add_argument("--ends-this-week", action="store_true")
    events.add_argument("--pokemon")
    events.add_argument("--country", type=str.upper)
    events.add_argument("--source-country", type=str.upper)
    events.add_argument("--category", choices=[category.value for category in Category])
    events.add_argument("--days", type=_positive_int, default=7)
    events.add_argument("--limit", type=_positive_int, default=50)
    return parser


def _positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def _collect(
    repository: SQLiteRepository, selected_source: str | None, config_path: Path = DEFAULT_CONFIG
) -> int:
    failed = False
    try:
        with Path(config_path).open("rb") as file:
            sources = tomllib.load(file)["sources"]
        if not isinstance(sources, dict) or not all(isinstance(value, dict) for value in sources.values()):
            raise ValueError("sources must contain TOML source tables")
        if selected_source and selected_source not in sources:
            raise ValueError(f"unknown source: {selected_source}")
    except (OSError, KeyError, ValueError) as error:
        print(f"configuration failed: {error}", file=sys.stderr)
        return 1
    source_ids = [selected_source] if selected_source else list(sources)
    for source_id in source_ids:
        config = sources[source_id]
        if config.get("enabled") is not True:
            if selected_source:
                print(f"{source_id}: disabled; no request sent", file=sys.stderr)
                return 1
            continue
        try:
            collector = (
                RssCollector(source_id, config)
                if config.get("type") == "rss"
                else COLLECTORS[source_id](config_path=config_path)
            )
        except (KeyError, TypeError, ValueError) as error:
            failed = True
            print(f"{source_id}: configuration failed: {error}", file=sys.stderr)
            continue
        repository.save_source(
            collector.source_id, collector.source_name, collector.source_url
        )
        run_id = repository.start_run(collector.source_id, datetime.now(timezone.utc))
        saved = 0
        try:
            events = deduplicate_events(collector.collect())
            changes: Counter[str] = Counter()
            for event in events:
                previous = repository.get_event(event.id)
                try:
                    event = collector.enrich(event, previous)
                except Exception as error:
                    print(f"{event.id}: detail skipped: {error}", file=sys.stderr)
                    if previous:
                        event = replace(previous, collected_at=event.collected_at)
                event = tag_event(event)
                changes[repository.save_event(event).value] += 1
                saved += 1
            repository.finish_run(
                run_id, datetime.now(timezone.utc), "SUCCESS", len(events)
            )
            summary = " ".join(f"{name}={count}" for name, count in sorted(changes.items()))
            print(f"{source_id}: collected={len(events)} {summary}")
        except Exception as error:
            failed = True
            repository.finish_run(
                run_id, datetime.now(timezone.utc), "FAILED", saved, str(error)
            )
            print(f"{source_id}: FAILED: {error}", file=sys.stderr)
    return int(failed)


def _tag(repository: SQLiteRepository) -> int:
    now = datetime.now(timezone.utc)
    tagged = 0
    events = repository.list_events()
    for event in events:
        updated = tag_event(event)
        if updated.pokemon != event.pokemon:
            repository.save_event(replace(updated, collected_at=now))
            tagged += 1
    print(f"scanned={len(events)} tagged={tagged}")
    return 0


def _draft(
    repository: SQLiteRepository, event_id: str, notes_path: Path | None = None,
    output: Path | None = None,
) -> int:
    event = repository.get_event(event_id)
    if event is None:
        print(f"event not found: {event_id}", file=sys.stderr)
        return 1
    try:
        notes = None
        if notes_path:
            with notes_path.open("rb") as file:
                notes = tomllib.load(file)
        draft = render_blog_draft(event, notes)
        if output:
            if output.suffix.lower() != ".md":
                raise ValueError("output must be a .md file")
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("x", encoding="utf-8", newline="\n") as file:
                file.write(draft)
            print(f"draft={output.resolve()}")
        else:
            print(draft)
    except (OSError, ValueError, TypeError) as error:
        print(f"draft failed: {error}", file=sys.stderr)
        return 1
    return 0


def _digest(repository: SQLiteRepository, args: argparse.Namespace) -> int:
    now = datetime.now(timezone.utc)
    today = datetime.now(KST).date()
    details = repository.get_recent_change_details(now - timedelta(days=args.days))
    changes = {event_id: value["types"] for event_id, value in details.items()}
    candidates = select_candidates(
        repository.list_events(), details, now, args.days, args.ending_days,
        args.focus, args.source_country,
    )
    if not candidates:
        print("블로그 후보가 없습니다.")
        return 0
    for candidate in candidates[: args.limit]:
        print(_format_event(candidate.event, changes, today, args.ending_days))
        print(f"선정 점수: {candidate.score} (편집 우선순위; 검색량·인기도 아님)")
        print(f"선정 이유: {', '.join(candidate.reasons)}")
        fields = [FIELD_LABELS.get(name, name) for name in candidate.changed_fields]
        print(f"변경 항목: {', '.join(fields) or '없음 / 신규 공지'}")
        print(f"추가 확인: {', '.join(candidate.checks)}")
        if candidate.related_ids:
            print(f"동일 출처 링크 묶음: {', '.join(candidate.related_ids)}")
        print()
    return 0


def _preview(repository: SQLiteRepository) -> int:
    collector = PokemonJapanCollector(max_pages=1)
    event = max(
        collector.collect(),
        key=lambda item: item.published_at or datetime.min.replace(tzinfo=timezone.utc),
    )
    previous = repository.get_event(event.id)
    print("[1/4] 목록 정규화")
    print(f"id: {event.id}")
    print(f"title: {event.title}")
    print(f"description: {event.description or '-'}")
    print(f"published_at: {event.published_at.isoformat() if event.published_at else '-'}")
    print(f"source_url: {event.source_url}")
    print(f"source_hash: {event.source_hash or event.content_hash}")

    try:
        enriched = collector.enrich(event)
    except Exception as error:
        print(f"detail_error: {error}", file=sys.stderr)
        enriched = collector.enrich(event, previous)
    enriched = tag_event(enriched)
    print("\n[2/4] 상세 페이지 보강")
    print(f"start_date: {enriched.start_date.isoformat() if enriched.start_date else '-'}")
    print(f"end_date: {enriched.end_date.isoformat() if enriched.end_date else '-'}")
    print(f"venue: {enriched.venue or '-'}")
    print(f"status: {enriched.status.value}")
    print(f"detail_hash: {enriched.detail_hash or '-'}")
    print(
        "detail_checked_at: "
        f"{enriched.detail_checked_at.isoformat() if enriched.detail_checked_at else '-'}"
    )

    change = detect_change(previous, enriched)
    print("\n[3/4] 변경 판정 (저장하지 않음)")
    print(f"previous: {'FOUND' if previous else 'NONE'}")
    print(f"change: {change.value}")

    print("\n[4/4] 블로그 후보 출력")
    changes = {enriched.id: {change.value}}
    print(_format_event(enriched, changes, datetime.now(KST).date(), 7))
    return 0


def _show_events(repository: SQLiteRepository, args: argparse.Namespace) -> int:
    now = datetime.now(timezone.utc)
    changes = repository.get_recent_changes(now - timedelta(days=args.days))
    today = datetime.now(KST).date()
    # ponytail: in-memory filtering is enough for a personal SQLite dataset; move to SQL if it grows.
    events = [
        event
        for event in repository.list_events()
        if _matches(event, args, changes, today)
    ]
    events.sort(key=lambda event: event.published_at.timestamp() if event.published_at else 0, reverse=True)
    if not events:
        print("조건에 맞는 이벤트가 없습니다.")
        return 0
    for event in events[: args.limit]:
        print(_format_event(event, changes, today, args.days))
        print()
    return 0


def _matches(
    event: PokemonEvent,
    args: argparse.Namespace,
    changes: dict[str, set[str]],
    today: date,
) -> bool:
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    end_date = event.end_date.date() if event.end_date else None
    start_date = event.start_date.date() if event.start_date else None
    checks = (
        not args.active or event.status == EventStatus.ACTIVE,
        not args.new or "NEW" in changes.get(event.id, set()),
        not args.updated or "UPDATED" in changes.get(event.id, set()),
        not args.ended or "ENDED" in changes.get(event.id, set()),
        not args.ending_soon
        or (end_date is not None and today <= end_date <= today + timedelta(days=args.days)),
        not args.starts_this_week
        or (start_date is not None and week_start <= start_date <= week_end),
        not args.ends_this_week
        or (end_date is not None and week_start <= end_date <= week_end),
        not args.pokemon
        or any(args.pokemon.casefold() in name.casefold() for name in event.pokemon),
        not args.country or event.country == args.country,
        not args.source_country or event.source_country == args.source_country,
        not args.category or event.category.value == args.category,
    )
    return all(checks)


def _format_event(
    event: PokemonEvent,
    changes: dict[str, set[str]],
    today: date,
    days: int,
) -> str:
    labels: list[str] = []
    labels.extend(
        label for label in ("NEW", "UPDATED", "ENDED") if label in changes.get(event.id, set())
    )
    if event.end_date and today <= event.end_date.date() <= today + timedelta(days=days):
        labels.append("ENDING SOON")
    heading = "".join(f"[{label}]" for label in labels) or "[EVENT]"
    lines = [f"{heading} {event.title}"]
    if event.start_date or event.end_date:
        lines.append(f"기간: {_date(event.start_date)} ~ {_date(event.end_date)}")
    if event.end_date and "ENDING SOON" in labels:
        lines.append(f"종료까지 {(event.end_date.date() - today).days}일")
    if event.published_at:
        lines.append(f"게시일: {event.published_at.date().isoformat()}")
    location = " / ".join(value for value in (event.country, event.region, event.venue) if value)
    lines.extend((f"지역: {location}", f"Source: {event.source_name}", f"URL: {event.source_url}"))
    lines.append(f"ID: {event.id}")
    return "\n".join(lines)


def _date(value: datetime | None) -> str:
    return value.date().isoformat() if value else "?"

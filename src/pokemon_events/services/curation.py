from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pokemon_events.models import Category, EventStatus, PokemonEvent


KST = timezone(timedelta(hours=9))
COLLAB_WORDS = ("콜라보", "협업", "コラボ", "collaboration", "collab")
GOODS_WORDS = ("굿즈", "인형", "피규어", "이모티콘", "グッズ", "ぬいぐるみ", "フィギュア",
               "goods", "merch", "plush", "apparel", "fragment", "프라그먼트", "스파오")
FIELD_LABELS = {"title": "제목", "description": "설명", "category": "분류", "country": "국가",
                "region": "지역", "venue": "장소", "start_date": "시작일", "end_date": "종료일",
                "source_url": "출처 링크", "published_at": "게시일", "status": "상태"}


@dataclass
class Candidate:
    event: PokemonEvent
    score: int
    reasons: list[str]
    changed_fields: list[str]
    checks: list[str]
    related_ids: list[str] = field(default_factory=list)


def select_candidates(
    events: list[PokemonEvent], details: dict[str, dict[str, set[str]]], now: datetime,
    days: int = 7, ending_days: int = 7, focus: str = "goods", source_country: str | None = None,
) -> list[Candidate]:
    if now.tzinfo is None or days < 1 or ending_days < 1 or focus not in {"goods", "all"}:
        raise ValueError("invalid curation time, window or focus")
    today = now.astimezone(KST).date()
    since = today - timedelta(days=days)
    candidates = []
    for event in events:
        if source_country and event.source_country != source_country:
            continue
        end = event.end_date.astimezone(KST).date() if event.end_date else None
        if event.status == EventStatus.ENDED or (end is not None and end < today):
            continue
        text = f"{event.title} {event.description or ''}".casefold()
        collab = event.category == Category.COLLAB or any(word in text for word in COLLAB_WORDS)
        goods = event.category == Category.GOODS or any(word in text for word in GOODS_WORDS)
        if focus == "goods" and not (collab or goods):
            continue
        change = details.get(event.id, {"types": set(), "fields": set()})
        published = event.published_at.astimezone(KST).date() if event.published_at else None
        recent = published is not None and since <= published <= today
        active = event.status in {EventStatus.UPCOMING, EventStatus.ACTIVE}
        updated = "UPDATED" in change["types"]
        new = "NEW" in change["types"] and (recent or active)
        ending = end is not None and today <= end <= today + timedelta(days=ending_days)
        if not (updated or new or ending):
            continue
        reasons = ["콜라보·협업" if collab else "굿즈·상품" if goods else "전체 주제"]
        score = 40 if collab else 30 if goods else 0
        if updated:
            reasons.append("기간 내 실제 정보 변경")
            score += 30
        if new:
            reasons.append("최근 공지 신규 수집" if recent else "예정·진행 중 소식 신규 수집")
            score += 20
        if ending:
            reasons.append(f"종료까지 {(end - today).days}일")
            score += 10
        checks = []
        if not event.published_at:
            checks.append("공지 게시일")
        if goods or collab:
            checks.extend(("판매·예약 시작일", "가격·통화", "판매처·국내 구매 가능 여부"))
        if event.category == Category.POPUP:
            if not event.start_date:
                checks.append("행사 시작일")
            if not event.venue:
                checks.append("행사 장소·구 기준 위치")
        checks.append("이미지 이용 조건·확보")
        candidates.append(Candidate(event, score, reasons,
                                    sorted(change["fields"]), checks))
    candidates.sort(key=lambda item: (-item.score,
                    -(item.event.published_at.timestamp() if item.event.published_at else 0), item.event.id))
    # ponytail: exact URL + publisher country only; translated campaign grouping needs verified IDs.
    groups: dict[tuple[str, str, str], Candidate] = {}
    for candidate in candidates:
        key = (candidate.event.source_country, candidate.event.country,
               _canonical_url(candidate.event.source_url))
        if key in groups:
            groups[key].related_ids.append(candidate.event.id)
            groups[key].changed_fields = sorted(set(groups[key].changed_fields + candidate.changed_fields))
        else:
            groups[key] = candidate
    return list(groups.values())


def _canonical_url(url: str) -> str:
    parts = urlsplit(url)
    query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
             if not key.casefold().startswith("utm_") and key.casefold() not in {"fbclid", "gclid"}]
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path,
                      urlencode(sorted(query)), ""))

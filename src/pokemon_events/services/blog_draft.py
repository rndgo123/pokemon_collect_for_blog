import re
from html import escape
from datetime import timedelta, timezone
from urllib.parse import urlsplit

from pokemon_events.models import Category, EventStatus, PokemonEvent

STATUS_LABEL = {EventStatus.UPCOMING: "예정", EventStatus.ACTIVE: "진행 중", EventStatus.ENDED: "종료"}
CATEGORY_LABEL = {"POPUP": "포켓몬팝업", "GAME": "포켓몬게임", "POKEMON_GO": "PokemonGO",
                  "GOODS": "포켓몬굿즈", "TCG": "포켓몬카드", "TRAVEL": "포켓몬여행", "COLLAB": "포켓몬콜라보"}
KST = timezone(timedelta(hours=9))


def render_blog_draft(event: PokemonEvent, notes: dict | None = None) -> str:
    """Short declarative prose; reviewed notes supplement facts, not copied article text."""
    notes = notes or {}
    if notes:
        _validate_notes(notes, event)
    goods = event.category in {Category.GOODS, Category.COLLAB}
    title = notes.get("title", f"[포켓몬] {event.title}")
    intro = notes.get("intro", [f"{_cell(event.source_name)}에 ‘{_cell(event.title)}’ 소식이 올라왔다."])
    rows = {"공지명": event.title} if not notes.get("facts") else {}
    if event.published_at:
        rows["공지 게시일 (한국 시간)"] = event.published_at.astimezone(KST).date().isoformat()
    if event.start_date or event.end_date:
        rows["관련 일정" if goods else "행사 기간"] = f"{_date(event.start_date)} ~ {_date(event.end_date)}"
    if event.venue:
        rows["장소"] = event.venue
    if event.region:
        rows["위치"] = " / ".join(value for value in (event.country, event.region) if value)
    if event.status != EventStatus.UNKNOWN:
        rows["상태"] = STATUS_LABEL[event.status]
    if event.pokemon:
        rows["관련 포켓몬"] = ", ".join(event.pokemon)
    for key, value in notes.get("facts", {}).items():
        if key in rows and rows[key] != value:
            raise ValueError(f"reviewed note conflicts with stored field: {key}")
        rows[key] = value
    lines = [f"# {_cell(title)}", ""]
    for paragraph in intro:
        lines.extend((paragraph, ""))
    lines.extend(("## 상품 정보" if goods else "## 행사 정보", "", "| 구분 | 내용 |", "|---|---|"))
    lines.extend(f"| {_cell(key)} | {_cell(value)} |" for key, value in rows.items())
    for section in notes.get("sections", []):
        lines.extend(("", f"## {_cell(section['heading'])}", ""))
        for paragraph in section["paragraphs"]:
            lines.extend((paragraph, ""))
    if not notes:
        lines.extend(("", "## 확인할 내용", ""))
        lines.append("가격과 판매·예약 일정은 원문에서 별도로 확인할 필요가 있다." if goods
                     else "방문 전 운영 시간과 예약·입장 조건을 확인하는 게 좋겠다.")
        if not goods and not event.venue:
            lines.extend(("", "상세 장소는 아직 저장된 정보에서 확인되지 않았다."))
    sources = notes.get("sources", []) + [{"label": event.source_name, "url": event.source_url}]
    lines.extend(("", "## 출처", ""))
    seen = set()
    for source in sources:
        _url(source["url"])
        if source["url"] not in seen:
            lines.append(f"- [{_cell(source['label'])}](<{source['url']}>)")
            seen.add(source["url"])
    lines.extend(("", _hashtags(event), ""))
    return "\n".join(lines)


def _validate_notes(notes: dict, event: PokemonEvent) -> None:
    if notes.get("reviewed") is not True or notes.get("source_url") != event.source_url:
        raise ValueError("notes require reviewed=true and the matching event source_url")
    allowed = {"reviewed", "source_url", "title", "intro", "facts", "sections", "sources"}
    if set(notes) - allowed:
        raise ValueError("unknown editorial note fields")
    if "title" in notes:
        _string(notes["title"])
    intro, facts = notes.get("intro", []), notes.get("facts", {})
    sections, sources = notes.get("sections", []), notes.get("sources", [])
    if not isinstance(intro, list) or not isinstance(facts, dict) or not isinstance(sections, list) or not isinstance(sources, list):
        raise ValueError("invalid editorial note structure")
    for text in intro:
        _string(text)
    for key, value in facts.items():
        _string(key)
        _string(value)
    for section in sections:
        if not isinstance(section, dict) or set(section) != {"heading", "paragraphs"}:
            raise ValueError("section requires heading and paragraphs")
        _string(section["heading"])
        if not isinstance(section["paragraphs"], list):
            raise ValueError("section paragraphs must be a list")
        for text in section["paragraphs"]:
            _string(text)
    for source in sources:
        if not isinstance(source, dict) or set(source) != {"label", "url"}:
            raise ValueError("source requires label and url")
        _string(source["label"])
        _string(source["url"])
        _url(source["url"])


def _url(value: str) -> None:
    parts = urlsplit(value)
    if parts.scheme not in {"https", "http"} or not parts.hostname or parts.username or parts.password or any(char.isspace() or char in "<>" for char in value):
        raise ValueError("source URL must be HTTP(S) without credentials or whitespace")


def _string(value) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("editorial text must be a non-empty string")


def _cell(value: str) -> str:
    return escape(" ".join(value.split()), quote=False).replace("|", "\\|").replace("[", "\\[").replace("]", "\\]")


def _date(value) -> str:
    return value.date().isoformat() if value else "미확인"


def _hashtags(event: PokemonEvent) -> str:
    tags = ["포켓몬"]
    if event.category not in {Category.GOODS, Category.COLLAB}:
        tags.append("포켓몬이벤트")
    tags.append(CATEGORY_LABEL.get(event.category.value, "포켓몬소식"))
    tags.extend(event.pokemon)
    country_tag = {"KR": "포켓몬코리아", "JP": "포켓몬재팬", "US": "미국포켓몬"}.get(event.source_country)
    if country_tag:
        tags.append(country_tag)
    cleaned = [re.sub(r"[^0-9A-Za-z가-힣_]", "", tag) for tag in tags]
    return " ".join(f"#{tag}" for tag in dict.fromkeys(cleaned) if tag)

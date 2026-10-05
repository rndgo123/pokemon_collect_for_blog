import re

from pokemon_events.models import EventStatus, PokemonEvent


STATUS_LABEL = {
    EventStatus.UPCOMING: "예정",
    EventStatus.ACTIVE: "진행 중",
    EventStatus.ENDED: "종료",
    EventStatus.UNKNOWN: "미확인",
}
CATEGORY_LABEL = {
    "POPUP": "팝업스토어",
    "GAME": "포켓몬게임",
    "POKEMON_GO": "PokemonGO",
    "GOODS": "포켓몬굿즈",
    "TCG": "포켓몬카드",
    "TRAVEL": "포켓몬여행",
    "COLLAB": "포켓몬콜라보",
}


def render_blog_draft(event: PokemonEvent) -> str:
    published = event.published_at.date().isoformat() if event.published_at else "미확인"
    period = (
        f"{_date(event.start_date)} ~ {_date(event.end_date)}"
        if event.start_date or event.end_date
        else "공식 공지에서 확인되지 않음"
    )
    location = (
        " / ".join(value for value in (event.country, event.region, event.venue) if value)
        if event.region or event.venue
        else ""
    )
    pokemon = ", ".join(event.pokemon) or "별도 태그 없음"
    description = _complete_description(event.description)
    lines = [
        f"# {event.title} | 공식 정보 정리",
        "",
        f"{event.source_name}에서 {published} 공개한 공식 공지를 정리했습니다.",
        "확인되지 않은 일정이나 장소는 임의로 추정하지 않았습니다.",
        "",
        "## 핵심 정보",
        "",
        f"- 상태: {STATUS_LABEL[event.status]}",
        f"- 기간: {period}",
        f"- 지역·장소: {location or '공식 공지에서 확인되지 않음'}",
        f"- 관련 포켓몬: {pokemon}",
        f"- 공식 게시일: {published}",
    ]
    if description:
        lines.extend(("", "## 공식 공지 요약", "", description))
    missing = []
    if not event.start_date and not event.end_date:
        missing.append("행사 기간")
    if not event.venue:
        missing.append("상세 장소")
    if missing:
        lines.extend(
            (
                "",
                "## 추가 확인이 필요한 정보",
                "",
                f"현재 구조화된 공식 데이터에는 {', '.join(missing)} 정보가 없습니다.",
                "후속 공식 공지가 등록되면 변경 이력을 다시 확인하겠습니다.",
            )
        )
    lines.extend(
        (
            "",
            "## 공식 출처",
            "",
            f"- {event.source_name}: {event.source_url}",
            "",
            _hashtags(event),
        )
    )
    return "\n".join(lines)


def _complete_description(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    if len(value) < 300:
        return value
    end = max(value.rfind(mark) for mark in ".!?。")
    return value[: end + 1] if end >= 0 else None


def _date(value) -> str:
    return value.date().isoformat() if value else "?"


def _hashtags(event: PokemonEvent) -> str:
    tags = ["포켓몬", "포켓몬이벤트"]
    category = CATEGORY_LABEL.get(event.category.value)
    if category:
        tags.append(category)
    tags.extend(event.pokemon)
    if "Pokémon GO" in event.title or "Pokemon GO" in event.title:
        tags.append("PokemonGO")
    tags.append("포켓몬코리아" if event.source_country == "KR" else "포켓몬재팬")
    cleaned = [re.sub(r"[^0-9A-Za-z가-힣_]", "", tag) for tag in tags]
    return " ".join(f"#{tag}" for tag in dict.fromkeys(cleaned) if tag)

import unittest
from datetime import datetime, timezone

from pokemon_events.models import Category, PokemonEvent
from pokemon_events.services import render_blog_draft


class BlogDraftTest(unittest.TestCase):
    def test_renders_facts_and_marks_missing_fields(self) -> None:
        event = PokemonEvent(
            id="pokemon_korea:1",
            title="야돈 이벤트 안내",
            description="야돈과 함께하는 공식 행사입니다.",
            category=Category.COLLAB,
            pokemon=["야돈"],
            country="KR",
            source_country="KR",
            source_name="Pokémon Korea",
            source_url="https://www.pokemonkorea.co.kr/news/6/1",
            published_at=datetime(2026, 9, 18, tzinfo=timezone.utc),
            collected_at=datetime(2026, 9, 18, tzinfo=timezone.utc),
            content_hash="hash",
        )
        draft = render_blog_draft(event)
        self.assertIn("야돈 이벤트 안내", draft)
        self.assertIn("| 관련 포켓몬 | 야돈 |", draft)
        self.assertNotIn("정리했습니다", draft)
        self.assertNotIn("행사 기간", draft)
        self.assertIn("#야돈", draft)
        self.assertNotIn("지역·장소: KR", draft)


if __name__ == "__main__":
    unittest.main()

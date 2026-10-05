import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

from pokemon_events.cli import main
from pokemon_events.models import Category, PokemonEvent
from pokemon_events.services.blog_draft import render_blog_draft
from pokemon_events.storage import SQLiteRepository


def event():
    return PokemonEvent(id="test", title="굿즈 공지", category=Category.GOODS,
                        country="US", source_name="Official", source_url="https://example.com/item",
                        published_at=datetime(2026, 10, 5, tzinfo=timezone.utc),
                        collected_at=datetime.now(timezone.utc), content_hash="test")


class DraftOutputTest(unittest.TestCase):
    def test_goods_no_fake_venue_or_launch_date_and_country_tag(self):
        draft = render_blog_draft(event())
        self.assertIn("| 공지 게시일 (한국 시간) | 2026-10-05 |", draft)
        self.assertNotIn("행사 기간", draft)
        self.assertNotIn("장소", draft)
        self.assertNotIn("출시일", draft)
        self.assertIn("#미국포켓몬", draft)
        self.assertNotIn("#포켓몬재팬", draft)

    def test_notes_require_review_matching_url_and_safe_types(self):
        for notes in (
            {"reviewed": False, "source_url": event().source_url},
            {"reviewed": True, "source_url": "https://example.com/other"},
            {"reviewed": True, "source_url": event().source_url, "facts": {"가격": 3000}},
            {"reviewed": True, "source_url": event().source_url, "sources": [
                {"label": "bad", "url": "javascript:alert(1)"}]},
        ):
            with self.subTest(notes=notes), self.assertRaises(ValueError):
                render_blog_draft(event(), notes)
        draft = render_blog_draft(event(), {"reviewed": True, "source_url": event().source_url,
            "intro": ["굿즈가 나왔다!"], "facts": {"가격": "3,000원 | 웹 기준"}})
        self.assertIn("3,000원 \\| 웹 기준", draft)
        self.assertIn("굿즈가 나왔다!", draft)

    def test_cli_saves_utf8_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "events.db"
            output = Path(directory) / "draft.md"
            with SQLiteRepository(db) as repository:
                repository.save_event(event())
            args = ["--db", str(db), "draft", "--id", "test", "--output", str(output)]
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(main(args), 0)
                original = output.read_text(encoding="utf-8")
                self.assertEqual(main(args), 1)
                self.assertEqual(output.read_text(encoding="utf-8"), original)
                self.assertEqual(main([*args[:-1], str(output.with_suffix('.txt'))]), 1)


if __name__ == "__main__":
    unittest.main()

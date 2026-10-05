import io
import tempfile
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from pokemon_events.cli import main
from pokemon_events.models import Category, PokemonEvent
from pokemon_events.storage import SQLiteRepository


class CliTest(unittest.TestCase):
    def test_new_event_output(self) -> None:
        event = PokemonEvent(
            id="pokemon-japan:1",
            title="new event",
            category=Category.OTHER,
            country="JP",
            source_name="Pokémon Japan",
            source_url="https://www.pokemon.co.jp/info/example.html",
            published_at=datetime.now(timezone.utc),
            collected_at=datetime.now(timezone.utc),
            content_hash="v1",
        )
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "events.db"
            with SQLiteRepository(database) as repository:
                repository.save_event(event)
            output = io.StringIO()
            with redirect_stdout(output):
                result = main(["--db", str(database), "events", "--new"])

        self.assertEqual(result, 0)
        self.assertIn("[NEW] new event", output.getvalue())
        self.assertIn("Source: Pokémon Japan", output.getvalue())

    def test_preview_traces_one_event_without_saving(self) -> None:
        event = PokemonEvent(
            id="pokemon_japan:1",
            title="preview event",
            category=Category.OTHER,
            country="JP",
            source_name="Pokémon Japan",
            source_url="https://www.pokemon.co.jp/info/example.html",
            published_at=datetime.now(timezone.utc),
            collected_at=datetime.now(timezone.utc),
            content_hash="v1",
        )

        class FakeCollector:
            def __init__(self, max_pages: int) -> None:
                self.max_pages = max_pages

            def collect(self) -> list[PokemonEvent]:
                return [event]

            def enrich(self, item: PokemonEvent, previous=None) -> PokemonEvent:
                return item

        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "events.db"
            output = io.StringIO()
            with patch("pokemon_events.cli.PokemonJapanCollector", FakeCollector):
                with redirect_stdout(output):
                    result = main(["--db", str(database), "preview"])
            with SQLiteRepository(database) as repository:
                self.assertEqual(repository.list_events(), [])

        self.assertEqual(result, 0)
        self.assertIn("[1/4] 목록 정규화", output.getvalue())
        self.assertIn("change: NEW", output.getvalue())
        self.assertIn("[NEW] preview event", output.getvalue())

    def test_updated_event_output(self) -> None:
        now = datetime.now(timezone.utc)
        event = PokemonEvent(
            id="pokemon_japan:updated",
            title="before",
            category=Category.OTHER,
            country="JP",
            source_name="Pokémon Japan",
            source_url="https://www.pokemon.co.jp/info/updated.html",
            collected_at=now,
            content_hash="v1",
        )
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "events.db"
            with SQLiteRepository(database) as repository:
                repository.save_event(event)
                repository.save_event(replace(event, title="after", content_hash="v2"))
            output = io.StringIO()
            with redirect_stdout(output):
                result = main(["--db", str(database), "events", "--updated"])

        self.assertEqual(result, 0)
        self.assertIn("[NEW][UPDATED] after", output.getvalue())

    def test_digest_excludes_old_initial_imports(self) -> None:
        now = datetime.now(timezone.utc)

        def event(event_id: str, title: str, published_at: datetime) -> PokemonEvent:
            return PokemonEvent(
                id=event_id,
                title=title,
                category=Category.OTHER,
                country="KR",
                source_name="Pokémon Korea",
                source_url=f"https://www.pokemonkorea.co.kr/news/6/{event_id}",
                published_at=published_at,
                collected_at=now,
                content_hash=event_id,
            )

        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "events.db"
            with SQLiteRepository(database) as repository:
                repository.save_event(event("recent", "recent event", now))
                repository.save_event(event("old", "old event", now - timedelta(days=100)))
            output = io.StringIO()
            with redirect_stdout(output):
                result = main(["--db", str(database), "digest", "--focus", "all"])

        self.assertEqual(result, 0)
        self.assertIn("recent event", output.getvalue())
        self.assertNotIn("old event", output.getvalue())


if __name__ == "__main__":
    unittest.main()

import unittest
from datetime import datetime, timezone

from pokemon_events.models import Category, PokemonEvent
from pokemon_events.services import tag_event


class PokemonTagsTest(unittest.TestCase):
    def test_tags_multilingual_aliases(self) -> None:
        event = PokemonEvent(
            id="event:1",
            title="ヤドン과 Pikachu 이벤트",
            description="야돈과 피카츄를 만나요",
            category=Category.OTHER,
            country="JP",
            source_name="official",
            source_url="https://example.com/event",
            collected_at=datetime.now(timezone.utc),
            content_hash="before",
        )
        tagged = tag_event(
            event,
            {"야돈": ("야돈", "ヤドン".casefold()), "피카츄": ("pikachu",)},
        )
        self.assertEqual(tagged.pokemon, ["야돈", "피카츄"])
        self.assertNotEqual(tagged.content_hash, event.content_hash)


if __name__ == "__main__":
    unittest.main()

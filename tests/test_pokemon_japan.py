import json
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from pokemon_events.collectors import PokemonJapanCollector
from pokemon_events.collectors.pokemon_japan import (
    _detail_fields,
    _event_country,
    _should_refresh,
)
from pokemon_events.models import Category, EventStatus, PokemonEvent


class PokemonJapanCollectorTest(unittest.TestCase):
    def test_collects_and_normalizes_api_result(self) -> None:
        payload = {
            "results": [
                {
                    "id": 42,
                    "title": " ポケモンイベント ",
                    "full_uniq": "https://www.pokemon.co.jp/info/example.html",
                    "start_date": "2026.09.18",
                    "txt_1": " 公式イベント ",
                    "term": "card",
                }
            ],
            "paging": {"nextPage": False},
        }
        config = """
[sources.pokemon_japan]
name = "Pokémon Japan"
list_url = "https://www.pokemon.co.jp/info/cat_event/"
api_url = "https://example.com/api"
country = "JP"
event_flag = 11
page_size = 20
request_delay_seconds = 0
timeout_seconds = 1
user_agent = "test"
"""
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "sources.toml"
            config_path.write_text(config, encoding="utf-8")
            with patch(
                "pokemon_events.collectors.pokemon_japan.fetch_bytes",
                return_value=json.dumps(payload).encode(),
            ):
                events = PokemonJapanCollector(config_path).collect()

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].id, "pokemon_japan:42")
        self.assertEqual(events[0].title, "ポケモンイベント")
        self.assertEqual(events[0].category, Category.TCG)
        self.assertEqual(events[0].published_at.isoformat(), "2026-09-18T00:00:00+09:00")
        self.assertEqual(len(events[0].content_hash), 64)

    def test_extracts_only_unambiguous_detail_fields(self) -> None:
        markup = """
<script>"<tr><th>開催期間</th><td>1月1日～2日</td></tr>"</script>
<table>
  <tr><th>開催期間</th><td>2026年8月28日（金）～30日（日）</td></tr>
  <tr><th>開催場所</th><td>モスコーニ・センター</td></tr>
</table>
"""
        start, end, venue, detail_hash = _detail_fields(markup, 2026)
        self.assertEqual(start.isoformat(), "2026-08-28T00:00:00+09:00")
        self.assertEqual(end.date().isoformat(), "2026-08-30")
        self.assertEqual(venue, "モスコーニ・センター")

        ambiguous = markup.replace(
            "</table>",
            "<tr><th>実施期間</th><td>9月1日～2日</td></tr>"
            "<tr><th>実施場所</th><td>別会場</td></tr></table>",
        )
        start, end, venue, changed_hash = _detail_fields(ambiguous, 2026)
        self.assertIsNone(start)
        self.assertIsNone(end)
        self.assertIsNone(venue)
        self.assertNotEqual(detail_hash, changed_hash)
        self.assertEqual(_event_country("アメリカ・カリフォルニア", "JP"), "US")

    def test_refreshes_when_source_changes(self) -> None:
        now = datetime(2026, 9, 18, tzinfo=timezone.utc)
        event = PokemonEvent(
            id="pokemon_japan:1",
            title="event",
            category=Category.OTHER,
            country="JP",
            source_name="Pokémon Japan",
            source_url="https://www.pokemon.co.jp/info/example.html",
            published_at=now,
            collected_at=now,
            content_hash="same",
            source_hash="same",
        )
        previous = replace(
            event,
            status=EventStatus.ACTIVE,
            detail_checked_at=now,
        )
        self.assertFalse(_should_refresh(event, previous, now, 30, 24))
        self.assertTrue(
            _should_refresh(replace(event, source_hash="changed"), previous, now, 30, 24)
        )


if __name__ == "__main__":
    unittest.main()

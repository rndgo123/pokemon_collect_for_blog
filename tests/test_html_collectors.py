import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pokemon_events.collectors import PokemonKoreaCollector, PokemonUniteCollector
from pokemon_events.collectors.pokemon_korea import _detail_fields
from pokemon_events.models import Category


CONFIG = """
[sources.pokemon_korea]
name = "Pokémon Korea"
list_url = "https://www.pokemonkorea.co.kr/news"
endpoint = "https://www.pokemonkorea.co.kr/ajax/news"
country = "KR"
request_delay_seconds = 0
timeout_seconds = 1
user_agent = "test"

[sources.pokemon_unite_jp]
name = "Pokémon UNITE Japan"
list_url = "https://www.pokemonunite.jp/ja/topics/"
country = "JP"
timeout_seconds = 1
user_agent = "test"
"""


class HtmlCollectorsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.config_path = Path(self.directory.name) / "sources.toml"
        self.config_path.write_text(CONFIG, encoding="utf-8")

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_pokemon_korea(self) -> None:
        markup = """
<li class="col-lg-3 col-6"><a href="/news/2/21094?cate=0&amp;sword=">
<h3> 포켓몬 카드 이벤트 </h3>
<ul class="list-split"><li>카드 게임</li><li>2026년 09월 09일</li></ul>
"""
        response = f"ignored#|#{markup}#|#1#|#".encode()
        with patch("pokemon_events.collectors.pokemon_korea.fetch_bytes", return_value=response):
            events = PokemonKoreaCollector(self.config_path).collect()

        self.assertEqual(events[0].id, "pokemon_korea:21094")
        self.assertEqual(events[0].category, Category.TCG)
        self.assertEqual(events[0].source_url, "https://www.pokemonkorea.co.kr/news/2/21094")

    def test_pokemon_korea_detail(self) -> None:
        markup = """
<div class="bx-board">
  <ul class="lst-connect"><li>트위터</li></ul>
  <p>세계 대회를 개최합니다.</p>
  <p>・개최 기간: 2026년 8월 28일(금)~30일(일)</p>
  <p>・개최 장소: 미국 캘리포니아 Moscone Center</p>
  <img src="/event.jpg">
</div><div class="bx-btm">
"""
        description, start, end, venue, detail_hash = _detail_fields(markup, 2026)
        self.assertEqual(description, "세계 대회를 개최합니다. ・개최 기간: 2026년 8월 28일(금)~30일(일) ・개최 장소: 미국 캘리포니아 Moscone Center")
        self.assertEqual(start.date().isoformat(), "2026-08-28")
        self.assertEqual(end.date().isoformat(), "2026-08-30")
        self.assertEqual(venue, "미국 캘리포니아 Moscone Center")
        self.assertEqual(len(detail_hash), 64)

    def test_pokemon_korea_distinguishes_shared_external_urls(self) -> None:
        items = """
<li class="col-lg-3 col-6"><a href="https://example.com/event">
<h3>첫 공지</h3><ul class="list-split"><li>이벤트</li><li>2026년 09월 09일</li></ul>
<li class="col-lg-3 col-6"><a href="https://example.com/event">
<h3>둘째 공지</h3><ul class="list-split"><li>이벤트</li><li>2026년 09월 09일</li></ul>
"""
        response = f"ignored#|#{items}#|#1#|#".encode()
        with patch("pokemon_events.collectors.pokemon_korea.fetch_bytes", return_value=response):
            events = PokemonKoreaCollector(self.config_path).collect()
        self.assertEqual(len({event.id for event in events}), 2)

    def test_pokemon_unite(self) -> None:
        markup = """
<li class="category_singleli listUp"><a href="https://www.pokemonunite.jp/ja/topics/news/20260904-1/">
<p><span class="category_year">2026</span><span class="category_day">09/04</span></p>
<ul><li class="category_nameli">ニュース</li></ul>
<h3 class="category_txt"> モルペコが参戦！ </h3></a></li>
"""
        with patch(
            "pokemon_events.collectors.pokemon_unite.fetch_bytes",
            return_value=markup.encode(),
        ):
            events = PokemonUniteCollector(self.config_path).collect()

        self.assertEqual(events[0].id, "pokemon_unite_jp:news:20260904-1")
        self.assertEqual(events[0].title, "モルペコが参戦！")
        self.assertEqual(events[0].category, Category.GAME)


if __name__ == "__main__":
    unittest.main()

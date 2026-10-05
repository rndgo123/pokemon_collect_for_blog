import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request

from pokemon_events.cli import main
from pokemon_events.collectors.http import fetch_bytes
from pokemon_events.collectors.rss import RssCollector
from pokemon_events.models import Category
from pokemon_events.storage import SQLiteRepository


CONFIG = {
    "enabled": True, "policy_approved": True, "name": "Test goods feed",
    "feed_url": "https://example.com/feed", "policy_url": "https://example.com/terms",
    "country": "JP", "category": "GOODS",
}
RSS = b'''<rss version="2.0"><channel><title>Test feed</title><item>
<guid>item-1</guid><title>Goods announcement</title>
<link>https://example.com/goods/1</link>
<pubDate>Mon, 05 Oct 2026 09:00:00 +0900</pubDate>
<description>Not collected</description></item></channel></rss>'''
ATOM = b'''<feed xmlns="http://www.w3.org/2005/Atom" xml:base="https://example.com/news/">
<entry><id>urn:item:1</id><title type="xhtml"><div xmlns="http://www.w3.org/1999/xhtml">New <b>goods</b></div></title>
<link href="one"/><updated>2026-10-05T01:00:00Z</updated></entry></feed>'''


class RssTest(unittest.TestCase):
    def test_rss_atom_metadata_and_stable_identity(self):
        collector = RssCollector("test", CONFIG)
        first = collector.parse(RSS)[0]
        changed = collector.parse(RSS.replace(b"Goods announcement", b"Updated goods"))[0]
        self.assertEqual(first.id, changed.id)
        self.assertNotEqual(first.content_hash, changed.content_hash)
        self.assertEqual(first.category, Category.GOODS)
        self.assertIsNone(first.description)
        self.assertEqual(first.published_at.isoformat(), "2026-10-05T00:00:00+00:00")
        atom = collector.parse(ATOM)[0]
        self.assertEqual(atom.title, "New goods")
        self.assertEqual(atom.source_url, "https://example.com/news/one")
        no_guid = RSS.replace(b"<guid>item-1</guid>", b"")
        self.assertEqual(collector.parse(no_guid)[0].id, collector.parse(no_guid)[0].id)

    def test_rejects_bad_or_empty_feed_and_unsafe_xml(self):
        collector = RssCollector("test", CONFIG)
        for payload in (
            b"<html/>", b'<rss version="2.0"><channel/></rss>',
            b'<!DOCTYPE rss [<!ENTITY x "expanded">]><rss version="2.0"/>',
            '<!DOCTYPE rss><rss version="2.0"/>'.encode("utf-16"),
            RSS.replace(b"Mon, 05 Oct 2026 09:00:00 +0900", b"invalid-date"),
            RSS.replace(b"https://example.com/goods/1", b"javascript:alert(1)"),
            b"x" * (2 * 1024 * 1024 + 1),
        ):
            with self.subTest(payload=payload[:50]), self.assertRaises(ValueError):
                collector.parse(payload)
        with self.assertRaises(ValueError):
            RssCollector("test", {**CONFIG, "policy_approved": False})
        with self.assertRaises(ValueError):
            RssCollector("test", {**CONFIG, "timeout_seconds": float("nan")})

    def test_cli_new_unchanged_updated_failed_and_disabled(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "sources.toml"
            database = Path(directory) / "test.db"
            config.write_text('''[sources.test]
type = "rss"
enabled = true
policy_approved = true
name = "Test goods feed"
feed_url = "https://example.com/feed"
policy_url = "https://example.com/terms"
country = "JP"
category = "GOODS"
''', encoding="utf-8")
            args = ["--db", str(database), "collect", "--source", "test", "--config", str(config)]
            output = io.StringIO()
            errors = io.StringIO()
            with patch("pokemon_events.collectors.rss.fetch_bytes", return_value=RSS) as fetch:
                with redirect_stdout(output), redirect_stderr(errors):
                    self.assertEqual(main(args), 0)
                    self.assertEqual(main(args), 0)
                    fetch.return_value = RSS.replace(b"Goods announcement", b"Updated goods")
                    self.assertEqual(main(args), 0)
                    fetch.return_value = b"<html/>"
                    self.assertEqual(main(args), 1)
                    config.write_text(config.read_text().replace("enabled = true", "enabled = false"))
                    fetch.reset_mock()
                    self.assertEqual(main(args), 1)
                    fetch.assert_not_called()
                    config.write_text(config.read_text().replace("enabled = false", "enabled = true")
                                      .replace("policy_approved = true", "policy_approved = false"))
                    self.assertEqual(main(args), 1)
                    fetch.assert_not_called()
            self.assertIn("NEW=1", output.getvalue())
            self.assertIn("UNCHANGED=1", output.getvalue())
            self.assertIn("UPDATED=1", output.getvalue())
            with SQLiteRepository(database) as repository:
                self.assertEqual(len(repository.list_events()), 1)
                self.assertEqual(repository.list_events()[0].title, "Updated goods")
                statuses = [row[0] for row in repository.connection.execute(
                    "SELECT status FROM collection_runs ORDER BY id"
                )]
                self.assertEqual(statuses, ["SUCCESS", "SUCCESS", "SUCCESS", "FAILED"])

    def test_http_stops_on_denial_and_limits_response(self):
        request = Request("https://example.com/feed")
        for code in (403, 429):
            with patch("pokemon_events.collectors.http.urlopen", side_effect=HTTPError(
                request.full_url, code, "denied", {}, None
            )) as fetch:
                with self.assertRaises(RuntimeError):
                    fetch_bytes(request, 1, 0)
                self.assertEqual(fetch.call_count, 1)
        with patch("pokemon_events.collectors.http.urlopen") as fetch:
            fetch.return_value.__enter__.return_value.read.return_value = b"1234"
            with self.assertRaises(ValueError):
                fetch_bytes(request, 1, 0, max_bytes=3)


if __name__ == "__main__":
    unittest.main()

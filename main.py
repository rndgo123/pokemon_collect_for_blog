import sys
from pathlib import Path


sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent / "src"))

from pokemon_events.cli import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())

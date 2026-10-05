import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def fetch_bytes(
    request: Request, timeout: float, retry_delay: float, max_bytes: int | None = None
) -> bytes:
    for attempt in range(3):
        try:
            with urlopen(request, timeout=timeout) as response:
                payload = response.read() if max_bytes is None else response.read(max_bytes + 1)
                if max_bytes is not None and len(payload) > max_bytes:
                    raise ValueError(f"response exceeds {max_bytes} bytes")
                return payload
        except HTTPError as error:
            if error.code in {403, 429}:
                raise RuntimeError(f"collection stopped: HTTP {error.code}") from error
            raise
        except (TimeoutError, URLError):
            if attempt == 2:
                raise
            time.sleep(retry_delay)
    raise AssertionError("unreachable")

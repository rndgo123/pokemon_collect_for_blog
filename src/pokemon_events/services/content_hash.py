import hashlib
import json


def hash_content(content: dict[str, object]) -> str:
    serialized = json.dumps(
        content, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(serialized).hexdigest()

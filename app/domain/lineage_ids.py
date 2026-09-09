import hashlib


def stable_lineage_id(kind: str, *parts: str | None) -> str:
    normalized = "\x1f".join((part or "").strip().casefold() for part in parts)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]
    return f"{kind}:{digest}"

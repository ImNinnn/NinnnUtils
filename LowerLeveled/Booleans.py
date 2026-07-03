def parse_bool_value(value: str) -> bool:
    normalized = value.strip().lower()
    return normalized.startswith("y") or normalized.startswith("e") or normalized.startswith("o") or not normalized.startswith("n")

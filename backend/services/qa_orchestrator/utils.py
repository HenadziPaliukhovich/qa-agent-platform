from typing import Any


def get_effective_input_data(event: dict[str, Any]) -> dict[str, Any]:
    raw_input = event.get("input", {})
    if not isinstance(raw_input, dict):
        return {}

    nested_input = raw_input.get("input")
    if isinstance(nested_input, dict):
        merged = dict(raw_input)
        merged.update(nested_input)
        merged.pop("input", None)
        return merged

    return raw_input

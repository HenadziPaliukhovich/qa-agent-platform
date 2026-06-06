"""
backend/shared/normalization.py

Centralised normalisation helpers shared across qa_orchestrator and qa_llm_gateway.

Previously this logic was duplicated in both services. Any change only needs to
happen here.
"""

from __future__ import annotations

import ast
import json
import re
from typing import Any


# ---------------------------------------------------------------------------
# JSON extraction
# ---------------------------------------------------------------------------

def extract_json_from_text(text: Any) -> Any:
    """Try to parse JSON from an LLM text response.

    Handles:
    - Already-parsed dict/list passthrough
    - Plain JSON string
    - ```json ... ``` fenced blocks
    - Partial JSON (auto-closes unclosed braces/brackets)
    """
    if isinstance(text, (dict, list)):
        return text

    if not isinstance(text, str):
        return None

    text = text.strip()

    def _try_load(candidate: str) -> Any:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            return None

    # 1. Plain JSON
    parsed = _try_load(text)
    if parsed is not None:
        return parsed

    # 2. Fenced ```json ... ```
    fenced_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced_match:
        parsed = _try_load(fenced_match.group(1))
        if parsed is not None:
            return parsed

    # 3. Bare object starting with {
    object_match = re.search(r"(\{.*)", text, re.DOTALL)
    if object_match:
        candidate = object_match.group(1).strip()

        parsed = _try_load(candidate)
        if parsed is not None:
            return parsed

        # Auto-close unclosed brackets
        open_curly = candidate.count("{")
        close_curly = candidate.count("}")
        open_square = candidate.count("[")
        close_square = candidate.count("]")

        if close_square < open_square:
            candidate += "]" * (open_square - close_square)
        if close_curly < open_curly:
            candidate += "}" * (open_curly - close_curly)

        parsed = _try_load(candidate)
        if parsed is not None:
            return parsed

    return None


# ---------------------------------------------------------------------------
# Text normalisation
# ---------------------------------------------------------------------------

# Common word-merge fixes produced by local LLMs (llama3, qwen3, mistral, gemma).
_WORD_MERGE_REPLACEMENTS: list[tuple[str, str]] = [
    (r"\bi\s+OS\b", "iOS"),
    (r"\bI\s+OS\b", "iOS"),
    (r"\bclient crashes or data loss\b", "client failure or incorrect error handling"),
    (r"\bcrashes or data loss\b", "incorrect client behavior"),
    (r"\bdata loss or inconsistent state\b", "inconsistent client or transaction state"),
    (r"\bSuccessfullogin\b", "Successful login"),
    (r"\bsuccessfullogin\b", "successful login"),
    (r"\bauthenticatedand\b", "authenticated and"),
    (r"\bandpassword\b", "and password"),
    (r"\bandusername\b", "and username"),
    (r"\bloginwith\b", "login with"),
    (r"\bwithvalid\b", "with valid"),
    (r"\bwithinvalid\b", "with invalid"),
    (r"\bvalidcredentials\b", "valid credentials"),
    (r"\binvalidcredentials\b", "invalid credentials"),
    (r"\binvalidusername\b", "invalid username"),
    (r"\binvalidpassword\b", "invalid password"),
    (r"\bvalidusername\b", "valid username"),
    (r"\bvalidpassword\b", "valid password"),
    (r"\bthedashboard\b", "the dashboard"),
    (r"\bthelogin\b", "the login"),
    (r"\bloginpage\b", "login page"),
    (r"\bdashboardpage\b", "dashboard page"),
    (r"\busernameandpassword\b", "username and password"),
    (r"\bauthenticationerror\b", "authentication error"),
    (r"\bvalidationerror\b", "validation error"),
    (r"\bEntera\b", "Enter a"),
    (r"\bOpena\b", "Open a"),
    (r"\bClickthe\b", "Click the"),
    (r"\bUseris\b", "User is"),
    (r"\bUserisnot\b", "User is not"),
    (r"\bredirectedtothe\b", "redirected to the"),
    (r"\bnotloggedin\b", "not logged in"),
    (r"\bseesavalidation\b", "sees a validation"),
    (r"\bseesanauthentication\b", "sees an authentication"),
    (r"\bresultfor\b", "result for"),
]


def normalize_text(value: Any) -> str:
    """Normalise a single text value coming from an LLM response.

    - Collapses whitespace
    - Fixes camelCase word merges common in local LLM output
    - Applies domain-specific QA phrase fixes
    """
    if not isinstance(value, str):
        value = str(value)

    text = value.strip()
    if not text:
        return text

    text = re.sub(r"\s+", " ", text)
    # Split run-together camelCase words (e.g. "loginWith" -> "login With")
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)

    for pattern, replacement in _WORD_MERGE_REPLACEMENTS:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    return text.strip()


# ---------------------------------------------------------------------------
# List helpers
# ---------------------------------------------------------------------------

def dedupe_preserve_order(items: list[str]) -> list[str]:
    """Remove duplicate strings while keeping insertion order."""
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        key = normalize_text(item).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def normalize_text_list(items: Any) -> list[str]:
    """Normalise a list of strings, stripping trailing periods and deduping."""
    if not isinstance(items, list):
        return []

    normalized: list[str] = []
    for item in items:
        value = normalize_text(item if isinstance(item, str) else str(item))
        if value:
            normalized.append(value.rstrip("."))

    return dedupe_preserve_order(normalized)


def normalize_steps(raw_steps: Any) -> list[str]:
    """Normalise test-case step list."""
    return normalize_text_list(raw_steps)


# ---------------------------------------------------------------------------
# Severity
# ---------------------------------------------------------------------------

_VALID_SEVERITIES = {"low", "medium", "high", "critical"}


def normalize_severity(value: Any) -> str:
    """Map any severity string to one of: low | medium | high | critical."""
    severity = normalize_text(str(value)).strip().lower()
    return severity if severity in _VALID_SEVERITIES else "medium"


# ---------------------------------------------------------------------------
# Risks
# ---------------------------------------------------------------------------

def normalize_risks(items: Any) -> list[dict]:
    """Normalise a list of risk items into a consistent dict structure.

    Accepts items as dict, plain string, or stringified dict (ast.literal_eval).
    """
    if not isinstance(items, list):
        return []

    normalized: list[dict] = []
    for item in items:
        if isinstance(item, dict):
            title = normalize_text(str(item.get("title", "")))
            if not title:
                continue
            normalized.append({
                "title": title,
                "severity": normalize_severity(item.get("severity", "medium")),
                "description": normalize_text(str(item.get("description", ""))),
            })
            continue

        if isinstance(item, str):
            parsed: Any = None
            try:
                parsed = ast.literal_eval(item)
            except Exception:
                parsed = None

            if isinstance(parsed, dict):
                title = normalize_text(str(parsed.get("title", "")))
                if not title:
                    continue
                normalized.append({
                    "title": title,
                    "severity": normalize_severity(parsed.get("severity", "medium")),
                    "description": normalize_text(str(parsed.get("description", ""))),
                })
                continue

            value = normalize_text(item)
            if value:
                normalized.append({"title": value, "severity": "medium", "description": ""})

    return normalized


def normalize_risk_strings(items: Any) -> list[str]:
    """Return risks as flat strings: 'Title (severity): description'."""
    result: list[str] = []
    for item in normalize_risks(items):
        title = normalize_text(str(item.get("title", "")))
        severity = normalize_text(str(item.get("severity", "")))
        description = normalize_text(str(item.get("description", "")))

        parts: list[str] = []
        if title:
            parts.append(f"{title} ({severity})" if severity else title)
        if description:
            parts.append(description)

        value = ": ".join(parts[:2])
        if value:
            result.append(value)
    return result


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

def normalize_test_cases(raw_test_cases: Any) -> list[dict]:
    """Normalise a list of test case items into a consistent dict structure.

    Each returned dict has: id, title, steps, expected_result.
    Accepts items as dict or plain string.
    """
    if not isinstance(raw_test_cases, list):
        return []

    normalized: list[dict] = []
    for index, item in enumerate(raw_test_cases, start=1):
        if isinstance(item, str):
            title = normalize_text(item)
            if not title:
                continue
            normalized.append({
                "id": f"TC-{index:03d}",
                "title": title,
                "steps": [],
                "expected_result": "",
            })
            continue

        if isinstance(item, dict):
            title = normalize_text(str(item.get("title", "")))
            if not title:
                continue
            normalized.append({
                "id": str(item.get("id", f"TC-{index:03d}")).strip() or f"TC-{index:03d}",
                "title": title,
                "steps": normalize_steps(item.get("steps", [])),
                "expected_result": normalize_text(str(item.get("expected_result", ""))),
            })

    return normalized


def normalize_simple_objects(
    raw_items: Any,
    required_key: str,
    fallback_status: str | None = None,
) -> list[dict]:
    """Normalise a list of simple objects that must contain `required_key`.

    Used e.g. for review findings: [{"finding": "...", "status": "..."}, ...]
    """
    if not isinstance(raw_items, list):
        return []

    normalized: list[dict] = []
    for item in raw_items:
        if isinstance(item, str):
            value = normalize_text(item)
            if value:
                entry: dict = {required_key: value}
                if fallback_status is not None:
                    entry["status"] = fallback_status
                normalized.append(entry)
            continue

        if isinstance(item, dict):
            value = normalize_text(str(item.get(required_key, "")))
            if not value:
                continue
            entry = dict(item)
            entry[required_key] = value
            normalized.append(entry)

    return normalized


# ---------------------------------------------------------------------------
# Summary + test-case recovery helper
# ---------------------------------------------------------------------------

def recover_summary_and_test_cases(llm_output: dict) -> tuple[str, list[dict]]:
    """Best-effort extraction of summary + test_cases from an LLM output dict.

    Falls back to alternative keys (cases, items, results) when primary keys
    are missing.
    """
    summary = normalize_text(str(llm_output.get("summary", "")))
    test_cases = normalize_test_cases(llm_output.get("test_cases", []))

    if summary and test_cases:
        return summary, test_cases

    if not summary:
        raw_text = normalize_text(str(llm_output))
        if raw_text:
            summary = raw_text

    if not test_cases and isinstance(llm_output, dict):
        for key in ("cases", "items", "results"):
            candidate = llm_output.get(key)
            parsed = normalize_test_cases(candidate)
            if parsed:
                test_cases = parsed
                break

    return summary, test_cases

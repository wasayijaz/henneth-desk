"""Root desk state-publication boundary.

The root terminal may publish ordinary desk state under /state, but CI-owner-only
artifacts belong only to the separate ci.henneth.app surface.
"""
from urllib.parse import unquote

CI_PRIVATE_STATE_FILES = (
    "company_documents.json",
    "company_briefs.json",
    "company_brief_receipts.json",
    "document_synthesis_queue.json",
)

CI_PRIVATE_STATE_PREFIXES = (
    "company_intel/",
)


def normalize_state_path(path):
    """Return a POSIX path relative to state/, or None for unsafe input."""
    if not isinstance(path, str):
        return None

    value = path
    for _ in range(3):
        try:
            decoded = unquote(value)
        except Exception:
            return None
        if decoded == value:
            break
        value = decoded

    value = value.replace("\\", "/").lstrip("/")
    while value.startswith("state/"):
        value = value[len("state/"):]

    parts = []
    for part in value.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            return None
        parts.append(part)
    return "/".join(parts)


def is_ci_private_state_path(path):
    """True when a request/build path is private to the CI surface."""
    normalized = normalize_state_path(path)
    if normalized is None:
        return True
    return normalized in CI_PRIVATE_STATE_FILES or any(
        normalized.startswith(prefix) for prefix in CI_PRIVATE_STATE_PREFIXES
    )

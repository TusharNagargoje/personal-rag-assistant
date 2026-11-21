import re
import ipaddress
import socket
from urllib.parse import urlparse
from typing import Tuple, List

# Common prompt injection patterns
INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions?",
    r"disregard\s+(all\s+)?(previous|prior|above)\s+instructions?",
    r"you\s+are\s+now\s+in\s+developer\s+mode",
    r"system\s*:\s*you\s+are",
    r"bypass\s+all\s+(filters|rules|restrictions)",
    r"reveal\s+(the\s+)?system\s+prompt",
    r"do\s+anything\s+now\s*\(dan\)",
]

ALLOWED_FILE_EXTENSIONS = {
    ".pdf", ".docx", ".txt", ".md", ".csv", ".xlsx", ".pptx"
}


def sanitize_input(text: str) -> str:
    """Strip dangerous control characters and normalize whitespace."""
    if not text:
        return ""
    # Strip null bytes and non-printable control characters except standard newlines/tabs
    sanitized = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", text)
    return sanitized.strip()


def check_prompt_injection(user_query: str) -> Tuple[bool, str]:
    """Check if the user input contains overt prompt injection attempts."""
    clean_query = user_query.lower()
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, clean_query, re.IGNORECASE):
            return True, "Potential prompt injection attempt detected."
    return False, ""


def validate_file(filename: str, file_size_bytes: int, max_mb: int = 50) -> Tuple[bool, str]:
    """Validate file extension and size."""
    import os
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_FILE_EXTENSIONS:
        return False, f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_FILE_EXTENSIONS))}"
    
    max_bytes = max_mb * 1024 * 1024
    if file_size_bytes > max_bytes:
        return False, f"File exceeds maximum allowed size of {max_mb}MB"
    
    return True, ""


def validate_public_http_url(url: str) -> Tuple[bool, str]:
    """Reject non-public URL targets to reduce server-side request forgery risk."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return False, "Only public HTTP(S) URLs are supported."
        hostname = parsed.hostname.rstrip(".").lower()
        if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".localhost"):
            return False, "Local network URLs cannot be ingested."
        addresses = {item[4][0] for item in socket.getaddrinfo(hostname, parsed.port or (443 if parsed.scheme == "https" else 80))}
        if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
            return False, "Local or non-public network URLs cannot be ingested."
        return True, ""
    except (ValueError, OSError):
        return False, "The URL could not be resolved to a public address."


def is_grounded_answer(answer: str, context_chunks: List[str]) -> bool:
    """
    Heuristic check to determine if the answer admits lack of context.
    Detects standard polite fallbacks to avoid hallucinations.
    """
    lower_ans = answer.lower()
    fallback_triggers = [
        "i do not have enough information",
        "i don't have enough information",
        "not mentioned in the provided context",
        "the provided documents do not contain",
        "i could not find any information",
        "the context does not provide",
    ]
    for trigger in fallback_triggers:
        if trigger in lower_ans:
            return True
    return len(context_chunks) > 0

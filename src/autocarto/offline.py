"""AUTOCARTO_OFFLINE=1 — air-gapped mode (Phase 5 / P5-T3).

A deployment-level guarantee, not a per-call preference: when set, every
network-capable choice in the system becomes structurally unavailable
rather than silently downgraded. The distinction matters -- silently
swapping in a mock/local substitute when a network path was explicitly
requested can mask exactly the kind of misconfiguration (e.g. this flag
left set from a previous session) a security-conscious deployment wants
surfaced, not hidden. So every call site wired to this flag raises a
clear, actionable error on conflict instead.

What "network-capable" means concretely, today: NvidiaLLM (real API
calls) and SentenceTransformerEmbedder (downloads model weights on first
use). Both MockLLM and the deterministic hash-embedding fallback need no
network ever, at any point, regardless of this flag -- they are simply
what remains reachable when the network-capable choices are refused.
"""

from __future__ import annotations

import os


def is_offline() -> bool:
    return os.environ.get("AUTOCARTO_OFFLINE") == "1"


class OfflineModeViolation(RuntimeError):
    """Raised when AUTOCARTO_OFFLINE=1 is set and a caller explicitly
    requested a choice that would require network access."""

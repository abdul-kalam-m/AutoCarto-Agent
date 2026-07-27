"""AUTOCARTO_OFFLINE=1 — air-gapped mode, Phase 5 / P5-T3.

Manual §11's acceptance: "assert zero sockets via test harness." The
zero-socket test below is the actual proof, not an inference from "we
didn't call the network-touching classes" -- it patches socket.socket
itself (what every stdlib network path bottoms out at: urllib,
http.client, and anything sentence-transformers/huggingface_hub might
try) so that creating *any* socket during the run raises immediately,
then runs the full demo harness end to end and confirms it completes
without ever hitting that patch.
"""

from __future__ import annotations

import os
import socket
from pathlib import Path
from unittest.mock import patch

import pytest

from autocarto.offline import OfflineModeViolation, is_offline


def test_is_offline_reads_the_env_var(monkeypatch):
    monkeypatch.delenv("AUTOCARTO_OFFLINE", raising=False)
    assert is_offline() is False
    monkeypatch.setenv("AUTOCARTO_OFFLINE", "1")
    assert is_offline() is True
    # Only the exact value "1" counts -- unset, "0", "" etc. are all "not offline".
    monkeypatch.setenv("AUTOCARTO_OFFLINE", "0")
    assert is_offline() is False


def test_offline_mode_rejects_nvidia_llm(monkeypatch):
    monkeypatch.setenv("AUTOCARTO_OFFLINE", "1")
    from autocarto.run_cli import _build_llm
    with pytest.raises(OfflineModeViolation):
        _build_llm("nvidia", None)


def test_offline_mode_does_not_block_mock_llm(monkeypatch):
    monkeypatch.setenv("AUTOCARTO_OFFLINE", "1")
    from autocarto.run_cli import _build_llm
    llm, provider, _model_id = _build_llm("mock", None)
    assert provider == "mock"


def test_offline_mode_rejects_sentence_transformer_embedder(monkeypatch):
    monkeypatch.setenv("AUTOCARTO_OFFLINE", "1")
    from autocarto.data_fabric.embedders import SentenceTransformerEmbedder
    with pytest.raises(OfflineModeViolation):
        SentenceTransformerEmbedder()


class _SocketCreationBlocked(AssertionError):
    """Distinct type so a real network attempt is unmistakable in a
    traceback, not confusable with an incidental AssertionError from
    elsewhere in the run."""


def _raise_on_socket_creation(*_args, **_kwargs):
    raise _SocketCreationBlocked(
        "socket.socket() was called during an AUTOCARTO_OFFLINE=1 run -- "
        "this is exactly what offline mode must prevent."
    )


def test_full_demo_run_creates_zero_sockets_under_offline_mode(tmp_path: Path, monkeypatch):
    """The end-to-end proof: the full demo harness (Gate 2, Gate 3b,
    hybrid retrieval, sandbox) runs to completion under AUTOCARTO_OFFLINE=1
    with socket creation itself patched to raise -- not skipped, not
    mocked around, the real code path with the real trap armed."""
    monkeypatch.setenv("AUTOCARTO_OFFLINE", "1")

    from autocarto import demo

    with patch.object(socket, "socket", side_effect=_raise_on_socket_creation):
        exit_code = demo.main(["--out", str(tmp_path)])

    assert exit_code == 0, "demo run failed under offline mode (see stdout/stderr above)"
    assert (tmp_path / "RUN_SUMMARY.json").exists()

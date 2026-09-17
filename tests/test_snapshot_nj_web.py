"""Refresh staging/promotion must not silently publish incomplete source data."""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("snapshot_nj_web", Path(__file__).parents[1] / "scripts/snapshot_nj_web.py")
snapshot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(snapshot)


def test_arcgis_rejects_pagination_stall(monkeypatch):
    monkeypatch.setattr(snapshot, "fetch", lambda *a: {"features": [], "exceededTransferLimit": True})
    with pytest.raises(RuntimeError, match="no progress"):
        snapshot.arcgis("https://example.test", "OBJECTID")


def test_arcgis_paginates_before_returning_complete_collection(monkeypatch):
    pages = iter([{"features": [{"id": 1}], "exceededTransferLimit": True}, {"features": [{"id": 2}]}])
    offsets = []
    def fetch(url, params):
        offsets.append(params["resultOffset"])
        return next(pages)
    monkeypatch.setattr(snapshot, "fetch", fetch)
    assert len(snapshot.arcgis("https://example.test", "OBJECTID")["features"]) == 2
    assert offsets == [0, 1]


def test_promotion_validates_all_hashes_before_any_write(tmp_path, monkeypatch):
    stage, destination = tmp_path / "stage", tmp_path / "live"
    stage.mkdir()
    destination.mkdir()
    monkeypatch.setattr(snapshot, "DEST", destination)
    files = {}
    for name in ("counties.geojson", "parks.geojson"):
        raw = b'{"type":"FeatureCollection","features":[]}'
        (stage / name).write_bytes(raw)
        files[name] = {"sha256": hashlib.sha256(raw).hexdigest()}
    manifest = {"manifest_version": 2, "sources": {"parks": snapshot.PARKS}, "files": files}
    (stage / "manifest.json").write_text(json.dumps(manifest))
    (stage / "parks.geojson").write_text("tampered")
    with pytest.raises(ValueError, match="Checksum mismatch"):
        snapshot.promote(stage)
    assert list(destination.iterdir()) == []


def test_promotion_copies_only_reviewed_bytes_without_fetch(tmp_path, monkeypatch):
    from autocarto.web.engine import DATA
    monkeypatch.setattr(snapshot, "DEST", tmp_path)
    def forbidden(*a, **k):
        raise AssertionError("Promotion must not fetch a new revision")
    monkeypatch.setattr(snapshot, "fetch", forbidden)
    snapshot.promote(DATA)
    for name in ("manifest.json", "counties.geojson", "parks.geojson"):
        assert (tmp_path / name).read_bytes() == (DATA / name).read_bytes()

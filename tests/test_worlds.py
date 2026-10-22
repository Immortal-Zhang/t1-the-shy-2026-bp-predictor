import json

from worlds_predictor import worlds


def test_official_confirmation_is_content_checked(tmp_path, monkeypatch):
    monkeypatch.setattr(worlds, "_fetch_official", lambda *args: b"<title>League of Legends Patch 26.20 Notes</title><p>The Worlds patch is here!</p>")
    output = tmp_path / "verification.json"
    result = worlds.verify_worlds_patch(report_path=output)
    assert result["status"] == "confirmed"
    assert result["official_patch"] == "26.20"
    assert len(result["page_sha256"]) == 64
    assert json.loads(output.read_text()) == result


def test_changed_official_patch_is_mismatch(monkeypatch):
    monkeypatch.setattr(worlds, "_fetch_official", lambda *args: b"<title>League of Legends Patch 26.21 Notes</title><p>The Worlds patch is here!</p>")
    assert worlds.verify_worlds_patch()["status"] == "mismatch"


def test_related_article_cards_are_not_patch_heading(monkeypatch):
    monkeypatch.setattr(worlds, "_fetch_official", lambda *args: b"<title>League of Legends Patch 26.20 Notes</title><p>The Worlds patch is here!</p><aside>League of Legends Patch 26.21 Notes</aside>")
    assert worlds.verify_worlds_patch()["status"] == "confirmed"


def test_unrelated_page_does_not_confirm(monkeypatch):
    monkeypatch.setattr(worlds, "_fetch_official", lambda *args: b"<title>League of Legends Patch 26.20 Notes</title><p>Other patch information</p><script>The Worlds patch is here!</script>")
    assert worlds.verify_worlds_patch()["status"] == "unverified"


def test_network_outage_does_not_confirm(monkeypatch):
    def unavailable(*args):
        raise TimeoutError("test-only timeout")

    monkeypatch.setattr(worlds, "_fetch_official", unavailable)
    result = worlds.verify_worlds_patch()
    assert result["status"] == "unverified"
    assert "TimeoutError" in result["reason"]


def test_non_official_source_rejected():
    try:
        worlds._fetch_official("https://example.org/untrusted", 1)
    except ValueError as exc:
        assert "official" in str(exc)
    else:
        raise AssertionError("Third-party URL was accepted")

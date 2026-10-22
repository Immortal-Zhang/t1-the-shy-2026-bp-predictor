"""Startup verification against Riot's official Worlds patch announcement."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PROJECT_ROOT / "configs" / "worlds2026.json"


class _VisibleText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hidden_depth = 0
        self.parts: list[str] = []
        self.heading_depth = 0
        self.headings: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in {"script", "style", "noscript"}:
            self.hidden_depth += 1
        if tag in {"title", "h1"}:
            self.heading_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self.hidden_depth:
            self.hidden_depth -= 1
        if tag in {"title", "h1"} and self.heading_depth:
            self.heading_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self.hidden_depth:
            self.parts.append(data)
            if self.heading_depth:
                self.headings.append(data)


def _fetch_official(url: str, timeout: float) -> bytes:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in {"www.leagueoflegends.com", "leagueoflegends.com", "lolesports.com", "www.lolesports.com"}:
        raise ValueError("Patch verification requires an HTTPS Riot official source")
    request = Request(url, headers={"User-Agent": "Worlds2026BPPredictor/0.1 (official patch verification)"})
    with urlopen(request, timeout=timeout) as response:
        # Refuse third-party redirects and unexpectedly large responses.
        if urlsplit(response.url).hostname not in {"www.leagueoflegends.com", "leagueoflegends.com", "lolesports.com", "www.lolesports.com"}:
            raise ValueError("Official source redirected outside Riot's supported domains")
        body = response.read(5_000_001)
        if len(body) > 5_000_000:
            raise ValueError("Official page exceeds the verification size limit")
        return body


def verify_worlds_patch(
    config_path: str | Path = DEFAULT_CONFIG,
    report_path: str | Path | None = None,
) -> dict:
    """Return confirmed/mismatch/unverified, never silently trust a cached check.

    This checks the configured official patch announcement's explicit Worlds
    statement. It cannot prove that Riot will never issue a later amendment.
    Network failures yield an observable unverified status, not confirmation.
    """
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    result = {
        "event": config["event"],
        "configured_patch": config["configured_patch"],
        "official_source": config["official_patch_url"],
        "official_event_url": config.get("official_event_url"),
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "status": "unverified",
        "official_patch": None,
        "page_sha256": None,
        "verification_scope": "Configured Riot announcement, not a guarantee against later rule amendments",
    }
    try:
        body = _fetch_official(config["official_patch_url"], float(config.get("verification_timeout_seconds", 8)))
        result["page_sha256"] = hashlib.sha256(body).hexdigest()
        parser = _VisibleText()
        parser.feed(body.decode("utf-8", errors="replace"))
        text = " ".join(" ".join(parser.parts).split())
        # Require an actual patch-note heading and explicit Worlds-patch prose;
        # a generic page mentioning both the patch and Worlds is insufficient.
        headings = " ".join(" ".join(parser.headings).split())
        patch_matches = set(re.findall(r"League of Legends Patch\s+(\d{2}\.\d{1,2})\s+Notes", headings, re.I))
        # Related-article cards on Riot pages list other patches. They are not
        # the article's title, nor evidence for this article's Worlds status.
        declares_worlds = re.search(r"\bWorlds\s+patch\b|patch\s+(?:we'll|we will)\s+be\s+seeing\s+our\s+year-defining\s+competitive", text[:3000], re.I)
        if len(patch_matches) != 1 or not declares_worlds:
            result["reason"] = "Official response did not unambiguously identify one Worlds patch"
        else:
            result["official_patch"] = patch_matches.pop()
            result["status"] = "confirmed" if result["official_patch"] == config["configured_patch"] else "mismatch"
            result["reason"] = "Riot patch-note heading and explicit Worlds statement matched" if result["status"] == "confirmed" else "Official patch differs from configured patch; reconcile configuration"
    except Exception as exc:
        result["reason"] = f"Official verification unavailable: {type(exc).__name__}: {exc}"
    if report_path is not None:
        path = Path(report_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return result

"""Review eight exact cached Sofascore events against newly retrieved public pages."""

import hashlib
import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from toto_ai.external_odds.schedule_evidence_admin import (
    review_prepared_schedule_evidence,
)

ROOT = Path("/Users/turshevr/toto-ai")
TASK = Path(__file__).resolve().parent
PREFLIGHT = (
    ROOT
    / "data/scheduler/morning-dispatch/preflight"
    / "drawing-12100-20260905T133000Z-fe49b1ba85febf3a"
)
LEDGER = ROOT / "data/schedule-evidence/ledger.json"
REVIEWS = LEDGER.parent / "reviews"
SNAPSHOTS = LEDGER.parent / "snapshots"
PAGES = {
    2: (
        "premierleague-source.html",
        "Premier League",
        "official",
        "https://www.premierleague.com/en/news/4675097",
        "Fulham",
        "Crystal Palace",
    ),
    4: (
        "qpr-source.html",
        "TNT Sports",
        "independent",
        "https://www.tntsports.co.uk/football/championship/2026-2027/queens-park-rangers-middlesbrough_mtc21887479/live.shtml",
        "Queens Park Rangers",
        "Middlesbrough",
    ),
    5: (
        "sheffield-source.html",
        "Portfolio Sports",
        "independent",
        "https://www.portfoliosports.com/football/championship/2026-09-05/sheffield-united-v-norwich-city/",
        "Sheffield United",
        "Norwich City",
    ),
    9: (
        "laliga-primary-source.html",
        "Sportschau",
        "independent",
        "https://www.sportschau.de/live-und-ergebnisse/fussball/spanien-primera-division/ma12187876/rayo-vallecano_racing-santander/spiel-spiele-und-ergebnisse",
        "Athletic Club",
        "Atlético Madrid",
    ),
    10: (
        "laliga-primary-source.html",
        "Sportschau",
        "independent",
        "https://www.sportschau.de/live-und-ergebnisse/fussball/spanien-primera-division/ma12187876/rayo-vallecano_racing-santander/spiel-spiele-und-ergebnisse",
        "Rayo Vallecano",
        "Racing Santander",
    ),
    11: (
        "laliga2-source.html",
        "LaLiga",
        "official",
        "https://iaas-public-front-pro.laliga.com/laliga-hypermotion/resultados",
        "Real Sporting",
        "Girona FC",
    ),
    12: (
        "laliga2-source.html",
        "LaLiga",
        "official",
        "https://iaas-public-front-pro.laliga.com/laliga-hypermotion/resultados",
        "Real Valladolid CF",
        "FC Andorra",
    ),
    14: (
        "shinnik-source.html",
        "FC Shinnik",
        "official",
        "https://shinnik.com/",
        "Шинник",
        "Ротор",
    ),
}
UTC = timezone.utc
EXPECTED = {
    2: "14:00",
    4: "14:00",
    5: "14:00",
    9: "14:15",
    10: "16:30",
    11: "14:15",
    12: "16:30",
    14: "14:00",
}
queue = json.loads((PREFLIGHT / "reviewed-schedule-queue-all15.json").read_text())
prepared = []
for position, (file, publisher, role, url, home, away) in PAGES.items():
    collection_root = PREFLIGHT / f"source-collector/event-{position:02}-live"
    document = json.loads(
        (collection_root / "schedule-source-candidates.json").read_text()
    )
    unsigned = {k: v for k, v in document.items() if k != "report_sha256"}
    assert any(
        hashlib.sha256(
            json.dumps(
                unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=ascii
            ).encode()
        ).hexdigest()
        == document["report_sha256"]
        for ascii in (True, False)
    )
    source = next(r for r in document["records"] if r["source_name"] == "Sofascore")
    source_path = collection_root / source["snapshot_path"]
    assert (
        hashlib.sha256(source_path.read_bytes()).hexdigest()
        == source["snapshot_sha256"]
    )
    raw = json.loads(source_path.read_text())
    event = next(
        r["entity"]
        for r in raw["results"]
        if r.get("entity", {}).get("id") == source["source_event_id"]
    )
    start = f"2026-09-05T{EXPECTED[position]}:00Z"
    assert source["starts_at"] == start
    assert (
        datetime.fromtimestamp(event["startTimestamp"], UTC)
        .isoformat()
        .replace("+00:00", "Z")
        == start
    )
    assert (
        event["homeTeam"]["name"] == source["home_name"]
        and event["awayTeam"]["name"] == source["away_name"]
    )
    assert event["status"]["type"] == "notstarted"
    page_path = TASK / file
    page = page_path.read_text()
    plain = re.sub(r"\s+", " ", html.unescape(re.sub("<[^>]+>", " ", page)))
    if position in (4, 5, 11, 12):
        sports = []
        for script in re.findall(
            r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
            page,
            re.S,
        ):
            try:
                d = json.loads(script)
            except ValueError:
                continue
            rows = d if isinstance(d, list) else d.get("@graph", [d])
            sports.extend(r for r in rows if "SportsEvent" in str(r.get("@type")))
        item = next(
            r for r in sports if home in r.get("name", "") and away in r.get("name", "")
        )
        assert (
            datetime.fromisoformat(item["startDate"].replace("Z", "+00:00"))
            .astimezone(UTC)
            .isoformat()
            .replace("+00:00", "Z")
            == start
        )
    elif position == 2:
        assert "15:00 UK time" in plain
        section = plain.split("Saturday 5 September", 1)[1].split(
            "Sunday 6 September", 1
        )[0]
        assert "Fulham v Crystal Palace" in section and "2026/27" in plain
    elif position in (9, 10):
        section = plain.split("05.09.2026", 1)[1]
        assert (
            "Athletic Club" in section
            and "Atlético Madrid" in section
            and "16:15" in section
            and "Rayo Vallecano" in section
            and "Racing Santander" in section
            and "18:30" in section
        )
        # Germany local September time (Europe/Berlin, UTC+02), not UTC display.
    else:
        assert "Шинник 5 сентября суббота 17:00 Ротор" in plain
        assert "04.09.2026" in plain
        # Yaroslavl local time is Europe/Moscow, UTC+03.
    evidence = []
    for path, name, kind, source_url, source_home, source_away, captured in (
        (
            source_path,
            "Sofascore",
            "independent",
            source["source_url"],
            source["home_name"],
            source["away_name"],
            source["captured_at"],
        ),
        (
            page_path,
            publisher,
            role,
            url,
            home,
            away,
            datetime.fromtimestamp(page_path.stat().st_mtime, UTC)
            .isoformat()
            .replace("+00:00", "Z"),
        ),
    ):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        dest = SNAPSHOTS / f"recovery-4997-{digest}{path.suffix}"
        if dest.exists():
            assert dest.read_bytes() == path.read_bytes()
        else:
            dest.write_bytes(path.read_bytes())
        evidence.append(
            dict(
                source_name=name,
                role=kind,
                source_url=source_url,
                snapshot=dest.name,
                snapshot_sha256=digest,
                home_team=source_home,
                away_team=source_away,
                starts_at=start,
                status="scheduled",
                captured_at=captured,
            )
        )
    q = queue["records"][position - 1]
    target = {
        k: q[k]
        for k in (
            "drawing_id",
            "drawing_number",
            "event_order",
            "target_event_id",
            "championship",
            "home_team",
            "away_team",
        )
    }
    target["sport"] = event["homeTeam"]["sport"]["slug"]
    assert target["sport"] == "football"
    assert (
        target["target_event_id"] == source["target_event_id"]
        and target["event_order"] == position - 1
    )
    observation = dict(
        observation_id=f"recovery-4997-event-{position:02}-20260904",
        sport="football",
        gender_age_class="men-senior",
        competition_aliases=list(
            dict.fromkeys([target["championship"], source["competition"]])
        ),
        home_entity=source["home_name"],
        home_aliases=list(
            dict.fromkeys([target["home_team"], source["home_name"], home])
        ),
        away_entity=source["away_name"],
        away_aliases=list(
            dict.fromkeys([target["away_team"], source["away_name"], away])
        ),
        starts_at=start,
        status="scheduled",
        conditional=False,
        reviewer="codex-local-evidence-review",
        reviewed_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    )
    review = dict(
        schema_version=1, target=target, observation=observation, sources=evidence
    )
    path = REVIEWS / f"prepared-recovery-4997-event-{position:02}.json"
    if path.exists():
        raise RuntimeError(f"Existing review must not be overwritten: {path}")
    path.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    kwargs = dict(
        ledger_path=LEDGER,
        reviews_dir=REVIEWS,
        snapshots_dir=SNAPSHOTS,
        review_path=path,
        expected_review_sha256=digest,
    )
    print(
        position,
        review_prepared_schedule_evidence(**kwargs, apply=False)["status"],
        flush=True,
    )
    prepared.append((position, kwargs))
for position, kwargs in prepared:
    result = review_prepared_schedule_evidence(**kwargs, apply=True)
    print(position, result["status"], flush=True)
(TASK / "source-review-summary.json").write_text(
    json.dumps(
        {
            "positions": [p for p, _ in prepared],
            "network_calls_during_review": 0,
            "reviewed_at": datetime.now(UTC).isoformat(),
            "review_files": [str(k["review_path"]) for _, k in prepared],
            "note": (
                "Event 10 input competition label is retained verbatim; sources "
                "identify Rayo-Racing as LaLiga EA SPORTS. This review confirms "
                "exact teams and kickoff only, without changing target categories."
            ),
        },
        indent=2,
    )
    + "\n"
)

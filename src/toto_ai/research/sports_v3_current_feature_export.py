"""Seal current-drawing research feature rows without scoring or release authority."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from toto_ai.external_odds.targets import parse_target_drawing
from toto_ai.sports_stats.v3_features import build_sports_v3_feature_table
from toto_ai.sports_stats.v3_probability import FEATURE_NAMES, seal
from toto_ai.sports_stats.v3_probability_features import augment_observed_features


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _utc(value):
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc)
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _stamp(value):
    return _utc(value).isoformat().replace("+00:00", "Z")


def _load(root, relative, expected):
    path = (Path(root) / relative).resolve()
    if not path.is_relative_to(Path(root).resolve()) or _sha256(path) != expected:
        raise ValueError("source path/hash binding")
    return json.loads(path.read_text()), path


def _history(document, fetched_at):
    rows = []
    for raw in document["payload"]["data"]:
        if raw.get("matchStatus") not in {"FINISHED", "AFTER_ET", "AFTER_PEN"}:
            continue
        home, away = raw["homeTeamId"], raw["awayTeamId"]
        suffix = "FtScore" if raw["matchStatus"] != "FINISHED" else "Score"
        rows.append(
            {
                "event_id": raw["id"],
                "kickoff": _utc(raw["kickoffUtc"]),
                "home_team_id": home,
                "away_team_id": away,
                "home_goals": int(raw["homeTeam" + suffix]),
                "away_goals": int(raw["awayTeam" + suffix]),
                "status": {"FINISHED": "FT", "AFTER_ET": "AET", "AFTER_PEN": "PEN"}[
                    raw["matchStatus"]
                ],
                "available_at": _utc(fetched_at),
            }
        )
    return rows


def seal_current_rows(*, root, source_evidence_path, final_input_path):
    """Return unreviewed original rows and complete BK-bound roster.

    This is deliberately a data-export boundary: no review decisions, model
    scoring, target labels, package generation, or operator authority.
    """
    root = Path(root).resolve()
    evidence_path = root / source_evidence_path
    evidence_bytes = evidence_path.read_bytes()
    evidence = json.loads(evidence_bytes)
    final_bytes = (root / final_input_path).read_bytes()
    final = json.loads(final_bytes)
    captured = _utc(final["captured_at"])
    target = parse_target_drawing(final["payload"], captured)
    if (
        target.drawing_id != evidence["drawing_id"]
        or target.drawing_number != evidence["drawing_number"]
    ):
        raise ValueError("final input drawing binding")
    event_by_order = {event.event_order: event for event in target.events}
    # The frozen final-input capture is the common feature as-of.  The drawing
    # close is later than several fixture kickoffs and therefore cannot be a
    # retrospective feature decision time.
    feature_cutoff = _stamp(captured)
    base_hash = hashlib.sha256(final_bytes).hexdigest()
    evidence_hash = hashlib.sha256(evidence_bytes).hexdigest()
    rows, roster = [], []
    for item in sorted(evidence["events"], key=lambda row: row["event_order"]):
        order = item["event_order"]
        event = event_by_order[order]
        fixture = item["target_fixture"]
        feature_sha = None
        kickoff = None
        status = "BK_FALLBACK_NO_PROVIDER_FIXTURE"
        if fixture is not None:
            target_doc, target_path = _load(
                root, fixture["path"], fixture["file_sha256"]
            )
            histories, source_hashes, history_provenance = (
                [],
                [fixture["file_sha256"], evidence_hash, base_hash],
                [],
            )
            for ledger in item["history_admission_ledger"]:
                doc, history_path = _load(
                    root, ledger["history_path"], ledger["history_sha256"]
                )
                fetched_at = doc["fetched_at"]
                histories.extend(_history(doc, fetched_at))
                source_hashes.append(ledger["history_sha256"])
                for raw in doc["payload"]["data"]:
                    if raw.get("matchStatus") in {"FINISHED", "AFTER_ET", "AFTER_PEN"}:
                        history_provenance.append(
                            {
                                "fixture_id": raw["id"],
                                "kickoff": _stamp(raw["kickoffUtc"]),
                                "completed_by": _stamp(fetched_at),
                                "completion_basis": "TERMINAL_OBSERVATION",
                                "source_sha256": ledger["history_sha256"],
                            }
                        )
            target_event = {
                "event_id": target_doc["provider_fixture_id"],
                "event_order": order,
                "home_team_id": target_doc["provider_home_team_id"],
                "away_team_id": target_doc["provider_away_team_id"],
                "kickoff": _utc(target_doc["payload"]["kickoffUtc"]),
            }
            kickoff = _stamp(target_doc["payload"]["kickoffUtc"])
            histories = list({row["event_id"]: row for row in histories}.values())
            table = build_sports_v3_feature_table(
                target_events=[target_event],
                completed_matches=histories,
                rolling_window=10,
                minimum_prior_matches=3,
            )
            features = dict.fromkeys(FEATURE_NAMES)
            features.update(table.rows[0].features)
            augment_observed_features(
                features, {"home": histories, "away": histories}, target_event, 3
            )
            features["bk_entropy"] = -sum(
                p * __import__("math").log(p) for p in event.bk_probabilities
            )
            row = seal(
                {
                    "kind": "RETROSPECTIVE_SPORTS_FEATURES_V1",
                    "drawing_number": target.drawing_number,
                    "event_order": order,
                    "event_id": target_doc["provider_fixture_id"],
                    "decision_cutoff": feature_cutoff,
                    "kickoff": kickoff,
                    "fetched_at": _stamp(captured),
                    "feature_available_at": None,
                    "bk_fetched_at": _stamp(captured),
                    "bk_quote_available_at": None,
                    "bk_probabilities": list(event.bk_probabilities),
                    "bk_margin": None,
                    "bk_input_sha256": final["probability_input_sha256"],
                    "source_hashes": sorted(set(source_hashes)),
                    "features": features,
                    "prior_counts": [
                        table.rows[0].features["home_prior_match_count"],
                        table.rows[0].features["away_prior_match_count"],
                    ],
                    "identity_status": "UNKNOWN",
                    "taxonomy": {"gender": None, "age_group": None, "squad_type": None},
                    "history": sorted(
                        {x["fixture_id"]: x for x in history_provenance}.values(),
                        key=lambda x: x["fixture_id"],
                    ),
                }
            )
            rows.append(row)
            feature_sha, status = row["sha256"], "PENDING_INDEPENDENT_CONSUMER_REVIEW"
        roster.append(
            {
                "row_id": f"{target.drawing_number}:{order}:{event.event_id}",
                "drawing_number": target.drawing_number,
                "event_order": order,
                "target_event_id": event.event_id,
                "decision_cutoff": feature_cutoff,
                "bk_probabilities": list(event.bk_probabilities),
                "bk_input_sha256": final["probability_input_sha256"],
                "bk_input_file_sha256": base_hash,
                "bk_fetched_at": _stamp(captured),
                "bk_quote_available_at": None,
                "provider_fixture_id": None
                if fixture is None
                else target_doc["provider_fixture_id"],
                "kickoff": kickoff,
                "status": status,
                "feature_sha256": feature_sha,
                "operator_compatible": False,
                "automatic_wagering": False,
            }
        )
    if len(roster) != 15 or len(rows) != 12:
        raise ValueError("expected 15 roster slots and 12 source lineages")
    return {
        "original_rows": rows,
        "roster": roster,
        "input_hashes": {
            "source_evidence_sha256": evidence_hash,
            "final_input_file_sha256": base_hash,
            "probability_input_sha256": final["probability_input_sha256"],
        },
    }

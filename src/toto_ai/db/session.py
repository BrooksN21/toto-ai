import sqlite3
from pathlib import Path

from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from toto_ai.db.models import Base, TeamAlias


def sqlite_url(db_path: str | Path) -> str:
    return f"sqlite+pysqlite:///{Path(db_path)}"


def init_db(db_path: str | Path = "data/toto.db") -> Engine:
    path = Path(db_path)
    if path.parent != Path("."):
        path.parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(sqlite_url(path))
    Base.metadata.create_all(engine)
    _add_missing_columns(engine)
    return engine


def open_readonly_db(db_path: str | Path) -> Engine:
    path = Path(db_path)
    if not path.is_file():
        raise ValueError(f"Database does not exist: {path}")
    uri = f"{path.resolve().as_uri()}?mode=ro"
    return create_engine(
        "sqlite+pysqlite://",
        creator=lambda: sqlite3.connect(uri, uri=True),
    )


def get_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)


def _add_missing_columns(engine: Engine) -> None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "team_aliases" in table_names:
        alias_columns = {
            column["name"] for column in inspector.get_columns("team_aliases")
        }
        if not {"country", "context"} <= alias_columns:
            _migrate_team_aliases_to_context_identity(engine)
            inspector = inspect(engine)
            table_names = set(inspector.get_table_names())
    with engine.begin() as connection:
        if "quotes" in table_names:
            existing_quote_columns = {
                column["name"] for column in inspector.get_columns("quotes")
            }
            required_quote_columns = {
                "norm_win_1": "FLOAT",
                "norm_draw": "FLOAT",
                "norm_win_2": "FLOAT",
            }
            for column_name, column_type in required_quote_columns.items():
                if column_name not in existing_quote_columns:
                    connection.execute(
                        text(
                            f"ALTER TABLE quotes ADD COLUMN "
                            f"{column_name} {column_type}"
                        )
                    )

        if "events" in table_names:
            existing_event_columns = {
                column["name"] for column in inspector.get_columns("events")
            }
            if "result_status" not in existing_event_columns:
                connection.execute(
                    text("ALTER TABLE events ADD COLUMN result_status VARCHAR")
                )

        if "external_collection_runs" in table_names:
            run_columns = {
                column["name"]
                for column in inspector.get_columns("external_collection_runs")
            }
            required_run_columns = {
                "target_fingerprint": "VARCHAR",
                "missing_start_horizon_days": "INTEGER",
                "requested_schedule_dates": "VARCHAR",
                "successful_schedule_dates": "VARCHAR",
                "failed_schedule_dates": "VARCHAR",
                "eligibility_status": "VARCHAR",
                "eligibility_earliest_start": "VARCHAR",
                "eligibility_latest_start": "VARCHAR",
                "eligibility_span_days": "INTEGER",
                "eligibility_missing_event_orders": "VARCHAR",
                "eligibility_totobrief_count": "INTEGER",
                "eligibility_provider_count": "INTEGER",
                "pinned_revalidation_summary": "TEXT",
                "quota_limit": "INTEGER",
                "quota_remaining": "INTEGER",
                "quota_used": "INTEGER",
                "quota_last_cost": "INTEGER",
            }
            for column_name, column_type in required_run_columns.items():
                if column_name not in run_columns:
                    connection.execute(
                        text(
                            "ALTER TABLE external_collection_runs "
                            f"ADD COLUMN {column_name} {column_type}"
                        )
                    )
            connection.execute(
                text(
                    "UPDATE external_collection_runs SET "
                    "eligibility_status = 'unknown', "
                    "eligibility_earliest_start = NULL, "
                    "eligibility_latest_start = NULL, "
                    "eligibility_span_days = 0, "
                    "eligibility_missing_event_orders = "
                    "'[0,1,2,3,4,5,6,7,8,9,10,11,12,13,14]', "
                    "eligibility_totobrief_count = 0, "
                    "eligibility_provider_count = 0 "
                    "WHERE target_fingerprint IS NULL"
                )
            )

        if "external_event_dispositions" in table_names:
            disposition_columns = {
                column["name"]
                for column in inspector.get_columns("external_event_dispositions")
            }
            if "match_orientation" not in disposition_columns:
                connection.execute(
                    text(
                        "ALTER TABLE external_event_dispositions "
                        "ADD COLUMN match_orientation VARCHAR"
                    )
                )
                connection.execute(
                    text(
                        "UPDATE external_event_dispositions "
                        "SET match_orientation = CASE "
                        "WHEN match_status = 'matched' THEN 'same' "
                        "ELSE 'none' END"
                    )
                )
            required_disposition_columns = {
                "provider_starts_at": "VARCHAR",
                "effective_starts_at": "VARCHAR",
                "effective_start_source": "VARCHAR",
                "provider_event_source_endpoint": "VARCHAR",
                "provider_event_request_fingerprint": "VARCHAR",
                "target_bk_probability_1": "FLOAT",
                "target_bk_probability_x": "FLOAT",
                "target_bk_probability_2": "FLOAT",
            }
            for column_name, column_type in required_disposition_columns.items():
                if column_name not in disposition_columns:
                    connection.execute(
                        text(
                            "ALTER TABLE external_event_dispositions "
                            f"ADD COLUMN {column_name} {column_type}"
                        )
                    )
            connection.execute(
                text(
                    "UPDATE external_event_dispositions "
                    "SET effective_start_source = 'unresolved' "
                    "WHERE effective_start_source IS NULL"
                )
            )

        if "team_registry_reviews" in table_names:
            review_columns = {
                column["name"]
                for column in inspector.get_columns("team_registry_reviews")
            }
            if "resolution_reason" not in review_columns:
                connection.execute(
                    text(
                        "ALTER TABLE team_registry_reviews "
                        "ADD COLUMN resolution_reason TEXT NOT NULL DEFAULT ''"
                    )
                )

        if "drawing_preparations" in table_names:
            preparation_columns = {
                column["name"]
                for column in inspector.get_columns("drawing_preparations")
            }
            if "updated_at" not in preparation_columns:
                connection.execute(
                    text(
                        "ALTER TABLE drawing_preparations "
                        "ADD COLUMN updated_at VARCHAR NOT NULL DEFAULT ''"
                    )
                )
            connection.execute(
                text(
                    "UPDATE drawing_preparations SET updated_at = created_at "
                    "WHERE updated_at = ''"
                )
            )

        if "drawing_result_snapshots" in table_names:
            snapshot_columns = {
                column["name"]
                for column in inspector.get_columns("drawing_result_snapshots")
            }
            if "ended_at" not in snapshot_columns:
                connection.execute(
                    text(
                        "ALTER TABLE drawing_result_snapshots "
                        "ADD COLUMN ended_at VARCHAR NOT NULL DEFAULT ''"
                    )
                )
                connection.execute(
                    text(
                        "UPDATE drawing_result_snapshots "
                        "SET ended_at = COALESCE(("
                        "SELECT drawings.ended_at FROM drawings "
                        "WHERE drawings.id = drawing_result_snapshots.drawing_id"
                        "), '') WHERE ended_at = ''"
                    )
                )
            if "hash_schema_version" not in snapshot_columns:
                connection.execute(
                    text(
                        "ALTER TABLE drawing_result_snapshots "
                        "ADD COLUMN hash_schema_version INTEGER "
                        "NOT NULL DEFAULT 1"
                    )
                )
            if "raw_snapshot_sha256" not in snapshot_columns:
                connection.execute(
                    text(
                        "ALTER TABLE drawing_result_snapshots "
                        "ADD COLUMN raw_snapshot_sha256 VARCHAR"
                    )
                )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS "
                    "ix_drawing_result_snapshots_raw_snapshot_sha256 "
                    "ON drawing_result_snapshots (raw_snapshot_sha256)"
                )
            )

        if "archived_packages" in table_names:
            archive_columns = {
                column["name"]
                for column in inspector.get_columns("archived_packages")
            }
            if "provenance" not in archive_columns:
                connection.execute(
                    text(
                        "ALTER TABLE archived_packages "
                        "ADD COLUMN provenance VARCHAR NOT NULL "
                        "DEFAULT 'legacy_import'"
                    )
                )
            if "archive_manifest_sha256" not in archive_columns:
                connection.execute(
                    text(
                        "ALTER TABLE archived_packages "
                        "ADD COLUMN archive_manifest_sha256 VARCHAR"
                    )
                )
            if "final_input_sha256" not in archive_columns:
                connection.execute(
                    text(
                        "ALTER TABLE archived_packages "
                        "ADD COLUMN final_input_sha256 VARCHAR"
                    )
                )
            if "probability_input_sha256" not in archive_columns:
                connection.execute(
                    text(
                        "ALTER TABLE archived_packages "
                        "ADD COLUMN probability_input_sha256 VARCHAR"
                    )
                )
            if "final_input_captured_at" not in archive_columns:
                connection.execute(
                    text(
                        "ALTER TABLE archived_packages "
                        "ADD COLUMN final_input_captured_at VARCHAR"
                    )
                )


def _migrate_team_aliases_to_context_identity(engine: Engine) -> None:
    """Rebuild the Phase-1 alias table so names can be scoped by competition."""
    legacy_table = "team_aliases_phase1"
    with engine.begin() as connection:
        connection.execute(
            text("ALTER TABLE team_aliases RENAME TO team_aliases_phase1")
        )
        for index_name in (
            "uq_team_alias_provider_team_id",
            "ix_team_alias_reviewed_lookup",
            "ix_team_aliases_team_id",
        ):
            connection.execute(text(f"DROP INDEX IF EXISTS {index_name}"))
        TeamAlias.__table__.create(connection)
        connection.execute(
            text(
                "INSERT INTO team_aliases ("
                "id, team_id, sport, alias, normalized_alias, transliterated_alias, "
                "source, provider, country, context, provider_team_id, provenance, "
                "confidence, reviewed, reviewer, reviewed_at, active, created_at, "
                "updated_at) "
                "SELECT a.id, a.team_id, a.sport, a.alias, a.normalized_alias, "
                "a.transliterated_alias, a.source, a.provider, "
                "COALESCE(t.country, ''), COALESCE(t.context, ''), "
                "a.provider_team_id, a.provenance, a.confidence, a.reviewed, "
                "a.reviewer, a.reviewed_at, a.active, a.created_at, a.updated_at "
                "FROM team_aliases_phase1 AS a "
                "JOIN team_entities AS t ON t.id = a.team_id"
            )
        )
        connection.execute(text(f"DROP TABLE {legacy_table}"))

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

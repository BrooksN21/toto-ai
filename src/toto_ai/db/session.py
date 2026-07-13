import sqlite3
from pathlib import Path

from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from toto_ai.db.models import Base


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
    if "quotes" not in inspector.get_table_names():
        return

    existing_columns = {
        column["name"]
        for column in inspector.get_columns("quotes")
    }
    required_columns = {
        "norm_win_1": "FLOAT",
        "norm_draw": "FLOAT",
        "norm_win_2": "FLOAT",
    }
    with engine.begin() as connection:
        for column_name, column_type in required_columns.items():
            if column_name not in existing_columns:
                connection.execute(
                    text(f"ALTER TABLE quotes ADD COLUMN {column_name} {column_type}")
                )

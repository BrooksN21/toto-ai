from pathlib import Path

from sqlalchemy import Engine, create_engine
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
    return engine


def get_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)

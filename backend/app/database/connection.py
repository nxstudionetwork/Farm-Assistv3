from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.config import settings

if settings.DATABASE_URL.startswith("sqlite"):
    # SQLite's default busy timeout is 5 seconds. Anything slower than that and
    # a request that arrives while another connection is committing fails
    # outright with "database is locked", which surfaces to the user as a 500
    # rather than as a brief wait. Waiting is always the better answer here.
    engine = create_engine(
        settings.DATABASE_URL,
        connect_args={
            "check_same_thread": False,
            "timeout": 30,
        },
        echo=settings.ECHO,
    )
else:
    engine = create_engine(settings.DATABASE_URL, echo=settings.ECHO)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

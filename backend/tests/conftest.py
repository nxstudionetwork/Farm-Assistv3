import atexit
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Every test module calls Base.metadata.drop_all(bind=engine) against the engine
# that app.database.connection builds from settings.DATABASE_URL. Those modules
# only set the URL when it is absent from os.environ, so an exported
# DATABASE_URL (CI, a sourced .env, a leftover shell variable) makes the suite
# drop every table in the real database. conftest.py is imported before any test
# module, so forcing the URL here makes the isolation unconditional.
#
# The file is per-process because these modules rebuild the schema around every
# test. A pytest run that lingers (the app keeps non-daemon worker threads
# alive after the results are printed) shares a fixed filename with the next
# run, and the two then drop and create each other's tables: the suite fails
# with "no such table: users" or "table ... already exists" on tables that have
# nothing to do with the test being run. One database per process removes that
# whole class of cross-run interference.
TEST_DB = BACKEND_DIR / "tests" / f"test_farm_assist_{os.getpid()}.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB}"


def _cleanup() -> None:
    for stale in (
        TEST_DB,
        Path(f"{TEST_DB}-journal"),
        Path(f"{TEST_DB}-wal"),
        Path(f"{TEST_DB}-shm"),
    ):
        try:
            stale.unlink()
        except OSError:
            pass


atexit.register(_cleanup)

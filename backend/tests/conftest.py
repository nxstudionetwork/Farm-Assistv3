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
os.environ["DATABASE_URL"] = f"sqlite:///{BACKEND_DIR / 'tests' / 'test_farm_assist.db'}"

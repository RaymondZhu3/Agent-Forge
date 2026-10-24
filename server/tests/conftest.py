import os
import tempfile

# Must be set before server modules create the engine.
_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["SERPAPI_MOCK"] = "1"
os.environ["NESSIE_MOCK"] = "1"
os.environ.pop("PRICE_INPUT_PER_MTOK", None)
os.environ.pop("PRICE_OUTPUT_PER_MTOK", None)

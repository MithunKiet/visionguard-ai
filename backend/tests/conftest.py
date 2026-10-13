import os

# Integration tests only target an explicitly supplied disposable database.
if os.environ.get("TEST_DATABASE_URL"):
    if not os.environ["TEST_DATABASE_URL"].rsplit("/", 1)[-1].endswith("_test"):
        raise RuntimeError("TEST_DATABASE_URL must identify a disposable *_test database")
    os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]

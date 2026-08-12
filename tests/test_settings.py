from config.settings import database_config


def test_explicit_sqlite_path_isolates_manual_runtime(monkeypatch, tmp_path):
    database = tmp_path / "manual.sqlite3"
    monkeypatch.setenv("CSRS_SQLITE_PATH", str(database))
    monkeypatch.setenv("DATABASE_URL", "postgresql://ignored:ignored@example.invalid/db")

    assert database_config() == {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": str(database),
    }

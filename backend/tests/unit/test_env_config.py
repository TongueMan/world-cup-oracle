from __future__ import annotations

from wcpa.shared import env


def test_database_url_can_be_disabled_for_tests(monkeypatch):
    env.load_env_file.cache_clear()
    monkeypatch.setenv("WCPA_DISABLE_DATABASE", "true")
    monkeypatch.setenv("WCPA_DATABASE_URL", "postgresql://wcpa:wcpa@localhost:5432/wcpa")

    assert env.database_url() == ""


def test_database_url_prefers_postgres_parts_over_legacy_local_default(monkeypatch):
    env.load_env_file.cache_clear()
    monkeypatch.setenv("WCPA_DISABLE_DATABASE", "false")
    monkeypatch.setenv("WCPA_DATABASE_URL", "postgresql://wcpa:wcpa@localhost:5432/wcpa")
    monkeypatch.setenv("WCPA_POSTGRES_DB", "wcpa")
    monkeypatch.setenv("WCPA_POSTGRES_USER", "postgre")
    monkeypatch.setenv("WCPA_POSTGRES_PASSWORD", "postgre")
    monkeypatch.setenv("WCPA_POSTGRES_HOST", "localhost")
    monkeypatch.setenv("WCPA_POSTGRES_PORT", "5432")

    assert env.database_url() == "postgresql://postgre:postgre@localhost:5432/wcpa"


def test_database_url_expands_env_placeholders(monkeypatch):
    env.load_env_file.cache_clear()
    monkeypatch.setenv("WCPA_DISABLE_DATABASE", "false")
    monkeypatch.setenv(
        "WCPA_DATABASE_URL",
        "postgresql://${WCPA_POSTGRES_USER}:${WCPA_POSTGRES_PASSWORD}@localhost:${WCPA_POSTGRES_PORT}/${WCPA_POSTGRES_DB}",
    )
    monkeypatch.setenv("WCPA_POSTGRES_DB", "wcpa")
    monkeypatch.setenv("WCPA_POSTGRES_USER", "postgre")
    monkeypatch.setenv("WCPA_POSTGRES_PASSWORD", "postgre")
    monkeypatch.setenv("WCPA_POSTGRES_PORT", "5432")

    assert env.database_url() == "postgresql://postgre:postgre@localhost:5432/wcpa"


def test_env_str_reads_docker_secret_file(monkeypatch, tmp_path):
    secret = tmp_path / "test_secret"
    secret.write_text("private-value\n", encoding="utf-8")
    monkeypatch.delenv("WCPA_TEST_SECRET", raising=False)
    monkeypatch.setenv("WCPA_TEST_SECRET_FILE", str(secret))

    assert env.env_str("WCPA_TEST_SECRET") == "private-value"

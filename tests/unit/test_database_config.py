from tendergraph.database.config import (
    DatabaseSettings,
)


def test_database_connection_uri() -> None:
    settings = DatabaseSettings(
        postgres_db="testdb",
        postgres_user="testuser",
        postgres_password="secret",
        postgres_host="localhost",
        postgres_port=5433,
    )

    assert settings.connection_uri == (
        "postgresql://"
        "testuser:secret@"
        "localhost:5433/testdb"
    )

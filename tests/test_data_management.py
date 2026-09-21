import sqlite3

import pytest

from src.accounts import create_account, list_accounts
from src.categories import seed_default_categories
from src.data_management import backup_bytes, reset_database, restore_database, validate_backup_bytes
from src.database import get_connection, initialize_database
from src.transactions import create_transaction, total_balance_cents


def setup_database(tmp_path):
    path = tmp_path / "financeiro.db"
    initialize_database(path)
    seed_default_categories(path)
    account_id = create_account("Conta fictícia", "conta_corrente", 100000, path)
    with get_connection(path) as connection:
        category_id = connection.execute("SELECT id FROM categories WHERE name = 'Alimentação'").fetchone()[0]
    create_transaction("Mercado fictício", 2500, "despesa", "2026-09-21", account_id, category_id, database_path=path)
    return path, account_id


def table_names(path):
    with sqlite3.connect(path) as connection:
        return {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}


def test_reset_creates_backup_preserves_schema_and_clears_data(tmp_path):
    path, _ = setup_database(tmp_path)
    backup_path = reset_database(path)

    assert backup_path.exists()
    assert {"accounts", "categories", "transactions"} <= table_names(path)
    with get_connection(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == 13


def test_backup_restore_preserves_records_relationships_and_balance(tmp_path):
    path, account_id = setup_database(tmp_path)
    backup_data = backup_bytes(path)
    reset_database(path)
    current_backup = restore_database(backup_data, path)

    assert current_backup.exists()
    assert list_accounts(path)[0]["id"] == account_id
    assert total_balance_cents(path) == 97500
    with get_connection(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 1
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_invalid_or_incompatible_backup_is_rejected(tmp_path):
    path, _ = setup_database(tmp_path)
    valid, message = validate_backup_bytes(b"not sqlite")
    assert not valid
    assert "SQLite" in message

    other = tmp_path / "other.db"
    with sqlite3.connect(other) as connection:
        connection.execute("CREATE TABLE unrelated (id INTEGER)")
    invalid = other.read_bytes()
    with pytest.raises(ValueError, match="incompatível"):
        restore_database(invalid, path)

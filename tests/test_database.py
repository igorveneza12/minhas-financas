import sqlite3

from src.accounts import create_account, list_accounts, money_to_cents
from src.database import get_connection, initialize_database


def test_database_is_initialized_with_expected_tables(tmp_path):
    database_path = tmp_path / "test.db"

    initialize_database(database_path)

    with get_connection(database_path) as connection:
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()[0]

    assert {"accounts", "categories", "transactions"} <= tables
    assert foreign_keys == 1


def test_account_can_be_created_and_retrieved(tmp_path):
    database_path = tmp_path / "test.db"
    initialize_database(database_path)

    account_id = create_account("Conta teste", "conta_corrente", 12345, database_path)
    accounts = list_accounts(database_path)

    assert account_id == accounts[0]["id"]
    assert accounts[0]["name"] == "Conta teste"
    assert accounts[0]["account_type"] == "conta_corrente"


def test_money_is_converted_to_cents_safely():
    assert money_to_cents("R$ 1.234,56") == 123456
    assert money_to_cents("10,005") == 1001
    assert money_to_cents("-5,50") == -550


def test_initial_balance_is_persisted_and_calculated(tmp_path):
    database_path = tmp_path / "test.db"
    initialize_database(database_path)
    create_account("Poupança teste", "poupanca", 98765, database_path)

    account = list_accounts(database_path)[0]

    assert account["initial_balance_cents"] == 98765
    assert account["balance_cents"] == 98765


def test_schema_rejects_invalid_transaction_amount(tmp_path):
    database_path = tmp_path / "test.db"
    initialize_database(database_path)

    with get_connection(database_path) as connection:
        connection.execute(
            "INSERT INTO accounts (name, account_type, initial_balance_cents) VALUES (?, ?, ?)",
            ("Conta teste", "dinheiro", 0),
        )
        connection.execute(
            "INSERT INTO categories (name, category_type) VALUES (?, ?)",
            ("Categoria teste", "despesa"),
        )
        try:
            connection.execute(
                """
                INSERT INTO transactions
                    (account_id, category_id, description, amount_cents, transaction_type, transaction_date)
                VALUES (1, 1, 'Lançamento inválido', 0, 'despesa', '2026-01-01')
                """
            )
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("A restrição de valor positivo não foi aplicada.")

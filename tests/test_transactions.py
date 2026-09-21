import sqlite3

import pytest

from src.accounts import (
    archive_account,
    create_account,
    delete_account,
    list_accounts,
    reactivate_account,
)
from src.categories import create_category, seed_default_categories
from src.database import get_connection, initialize_database
from src.transactions import (
    create_transaction,
    delete_transaction,
    list_transactions,
    monthly_comparison,
    monthly_expenses_by_category,
    monthly_totals,
    total_balance_cents,
    update_transaction,
)


def setup_database(tmp_path):
    path = tmp_path / "financeiro.db"
    initialize_database(path)
    seed_default_categories(path)
    account_id = create_account("Conta teste", "conta_corrente", 100000, path)
    with get_connection(path) as connection:
        categories = {
            row["name"]: row["id"]
            for row in connection.execute("SELECT id, name FROM categories")
        }
    return path, account_id, categories


def test_default_categories_are_idempotent(tmp_path):
    path, _, _ = setup_database(tmp_path)
    seed_default_categories(path)
    with get_connection(path) as connection:
        count = connection.execute("SELECT count(*) FROM categories").fetchone()[0]
    assert count == 13


def test_custom_category_is_persisted_and_duplicate_is_rejected(tmp_path):
    path, _, _ = setup_database(tmp_path)
    category_id = create_category("Pets", "despesa", path)
    assert category_id > 0
    with pytest.raises(ValueError, match="Já existe"):
        create_category("Pets", "despesa", path)


def test_initialization_preserves_existing_data(tmp_path):
    path, account_id, categories = setup_database(tmp_path)
    create_transaction("Receita preservada", 1000, "receita", "2026-01-01", account_id, categories["Salário"], database_path=path)
    initialize_database(path)
    rows = list_transactions(path)
    assert len(rows) == 1
    assert rows[0]["description"] == "Receita preservada"


def test_transaction_persists_and_filters(tmp_path):
    path, account_id, categories = setup_database(tmp_path)
    transaction_id = create_transaction(
        "Salário de teste", 250000, "receita", "2026-09-10", account_id, categories["Salário"], database_path=path
    )
    create_transaction(
        "Mercado fictício", 5000, "despesa", "2026-08-10", account_id, categories["Alimentação"], database_path=path
    )

    rows = list_transactions(path, year=2026, month=9, transaction_type="receita", account_id=account_id)
    assert rows[0]["id"] == transaction_id
    assert rows[0]["amount_cents"] == 250000
    assert len(list_transactions(path, year=2026, month=9)) == 1


def test_invalid_amount_and_category_type_are_rejected(tmp_path):
    path, account_id, categories = setup_database(tmp_path)
    with pytest.raises(ValueError, match="maior que zero"):
        create_transaction("Teste", 0, "despesa", "2026-09-01", account_id, categories["Alimentação"], database_path=path)
    with pytest.raises(ValueError, match="compatível"):
        create_transaction("Teste", 100, "despesa", "2026-09-01", account_id, categories["Salário"], database_path=path)


def test_update_rejects_category_from_different_transaction_type(tmp_path):
    path, account_id, categories = setup_database(tmp_path)
    transaction_id = create_transaction(
        "Despesa teste",
        100,
        "despesa",
        "2026-09-01",
        account_id,
        categories["Alimentação"],
        database_path=path,
    )

    with pytest.raises(ValueError, match="compatível"):
        update_transaction(
            transaction_id,
            "Receita inválida",
            100,
            "receita",
            "2026-09-01",
            account_id,
            categories["Alimentação"],
            database_path=path,
        )


def test_balance_recalculates_after_update_and_delete(tmp_path):
    path, account_id, categories = setup_database(tmp_path)
    transaction_id = create_transaction("Receita", 10000, "receita", "2026-09-01", account_id, categories["Salário"], database_path=path)
    assert total_balance_cents(path) == 110000
    update_transaction(transaction_id, "Receita atualizada", 20000, "receita", "2026-09-01", account_id, categories["Salário"], database_path=path)
    assert total_balance_cents(path) == 120000
    delete_transaction(transaction_id, path)
    assert total_balance_cents(path) == 100000


def test_monthly_result_excludes_initial_balance_and_empty_months_are_zero(tmp_path):
    path, account_id, categories = setup_database(tmp_path)
    create_transaction("Despesa", 1250, "despesa", "2026-03-05", account_id, categories["Lazer"], database_path=path)
    assert monthly_totals(2026, 3, path) == {"receita": 0, "despesa": 1250}
    assert monthly_totals(2026, 4, path) == {"receita": 0, "despesa": 0}
    comparison = monthly_comparison(2026, path)
    assert len(comparison) == 12
    assert comparison[3]["receitas_cents"] == 0
    assert comparison[3]["despesas_cents"] == 0
    assert monthly_expenses_by_category(2026, 4, path) == []


def test_database_trigger_preserves_type_consistency(tmp_path):
    path, account_id, categories = setup_database(tmp_path)
    with get_connection(path) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """INSERT INTO transactions
                (account_id, category_id, description, amount_cents, transaction_type, transaction_date)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (account_id, categories["Salário"], "Incompatível", 100, "despesa", "2026-01-01"),
            )


def test_account_without_transactions_can_be_deleted(tmp_path):
    path, account_id, _ = setup_database(tmp_path)

    delete_account(account_id, path)

    assert list_accounts(path) == []


def test_account_with_transactions_cannot_be_deleted(tmp_path):
    path, account_id, categories = setup_database(tmp_path)
    create_transaction(
        "Histórico fictício",
        1000,
        "receita",
        "2026-01-01",
        account_id,
        categories["Salário"],
        database_path=path,
    )

    with pytest.raises(ValueError, match="não pode ser excluída"):
        delete_account(account_id, path)
    assert len(list_transactions(path)) == 1


def test_archived_account_preserves_history_and_balance(tmp_path):
    path, account_id, categories = setup_database(tmp_path)
    create_transaction(
        "Receita arquivada",
        2500,
        "receita",
        "2026-01-01",
        account_id,
        categories["Salário"],
        database_path=path,
    )

    archive_account(account_id, path)

    assert list_accounts(path) == []
    assert list_accounts(path, include_archived=True)[0]["active"] == 0
    assert len(list_transactions(path)) == 1
    assert total_balance_cents(path) == 102500


def test_archived_account_cannot_receive_new_transactions(tmp_path):
    path, account_id, categories = setup_database(tmp_path)
    archive_account(account_id, path)

    with pytest.raises(ValueError, match="conta selecionada"):
        create_transaction(
            "Novo lançamento",
            1000,
            "despesa",
            "2026-01-01",
            account_id,
            categories["Alimentação"],
            database_path=path,
        )


def test_archived_account_can_be_reactivated(tmp_path):
    path, account_id, categories = setup_database(tmp_path)
    archive_account(account_id, path)
    reactivate_account(account_id, path)

    create_transaction(
        "Lançamento após reativação",
        1000,
        "despesa",
        "2026-01-01",
        account_id,
        categories["Alimentação"],
        database_path=path,
    )

    assert list_accounts(path)[0]["active"] == 1
    assert total_balance_cents(path) == 99000

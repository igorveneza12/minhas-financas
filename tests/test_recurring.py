from datetime import date

import pytest

from src.accounts import create_account, list_accounts
from src.categories import seed_default_categories
from src.database import get_connection, initialize_database
from src.recurring import create_recurring, delete_recurring, generate_occurrences, list_occurrences, list_recurring, occurrence_status, pay_occurrence, recurring_summary, set_recurring_status, update_recurring


def setup_db(tmp_path):
    path = tmp_path / "financeiro.db"
    initialize_database(path)
    seed_default_categories(path)
    account = create_account("Conta recorrente", "conta_corrente", 100000, path)
    with get_connection(path) as connection:
        category = connection.execute("SELECT id FROM categories WHERE name = 'Moradia'").fetchone()[0]
    recurring = create_recurring("Aluguel", category, account, 150000, 31, "2026-01-01", database_path=path)
    return path, account, category, recurring


def test_monthly_generation_is_idempotent_and_handles_short_months(tmp_path):
    path, _, _, recurring = setup_db(tmp_path)
    assert generate_occurrences(2026, 2, path) == 1
    assert generate_occurrences(2026, 2, path) == 0
    row = list_occurrences(2026, 2, database_path=path)[0]
    assert row["due_date"] == "2026-02-28"
    assert row["recurring_id"] == recurring


def test_payment_creates_one_expense_and_updates_balance(tmp_path):
    path, _, _, _ = setup_db(tmp_path)
    row = list_occurrences(2026, 1, database_path=path)[0]
    transaction_id = pay_occurrence(row["id"], 160000, "2026-01-05", path)
    assert transaction_id > 0
    assert occurrence_status(list_occurrences(2026, 1, database_path=path)[0]) == "Paga"
    assert list_accounts(path)[0]["balance_cents"] == -60000
    with pytest.raises(ValueError, match="já paga"):
        pay_occurrence(row["id"], 1, "2026-01-06", path)


def test_variable_amount_and_pause_stop_future_generation(tmp_path):
    path, _, category, recurring = setup_db(tmp_path)
    set_recurring_status(recurring, "paused", path)
    assert generate_occurrences(2026, 3, path) == 0
    set_recurring_status(recurring, "active", path)
    with get_connection(path) as connection:
        connection.execute("UPDATE recurring_expenses SET expected_amount_cents = ? WHERE id = ?", (175000, recurring))
    generate_occurrences(2026, 3, path)
    row = list_occurrences(2026, 3, database_path=path)[0]
    assert row["expected_amount_cents"] == 175000
    assert recurring_summary(2026, 3, path)["pendentes_cents"] == 175000


def test_end_date_excludes_later_months(tmp_path):
    path, _, category, recurring = setup_db(tmp_path)
    with get_connection(path) as connection:
        connection.execute("UPDATE recurring_expenses SET end_date = ? WHERE id = ?", ("2026-01-31", recurring))
    assert generate_occurrences(2026, 2, path) == 0


def test_update_changes_future_expected_amount(tmp_path):
    path, _, category, recurring = setup_db(tmp_path)
    update_recurring(recurring, "Aluguel atualizado", category, 1, 175000, 15, None, path)
    generate_occurrences(2026, 4, path)
    row = list_occurrences(2026, 4, database_path=path)[0]
    assert row["description"] == "Aluguel atualizado"
    assert row["expected_amount_cents"] == 175000


def test_recurring_remains_visible_without_selected_month_occurrence(tmp_path):
    path, _, _, recurring = setup_db(tmp_path)
    assert [row["id"] for row in list_recurring("Ativas", path)] == [recurring]
    assert list_occurrences(2025, 1, database_path=path) == []


def test_recurring_status_filter_lists_paused_as_inactive(tmp_path):
    path, _, _, recurring = setup_db(tmp_path)
    set_recurring_status(recurring, "paused", path)
    assert list_recurring("Ativas", path) == []
    assert list_recurring("Inativas", path)[0]["status"] == "paused"


def test_delete_recurring_removes_unpaid_forecasts(tmp_path):
    path, _, _, recurring = setup_db(tmp_path)
    generate_occurrences(2026, 1, path)
    delete_recurring(recurring, path)
    assert list_recurring("Todos", path) == []
    assert list_occurrences(2026, 1, database_path=path) == []


def test_delete_recurring_preserves_paid_history_and_blocks_delete(tmp_path):
    path, _, _, recurring = setup_db(tmp_path)
    occurrence = list_occurrences(2026, 1, database_path=path)[0]
    pay_occurrence(occurrence["id"], 150000, "2026-01-05", path)

    with pytest.raises(ValueError, match="pagamentos"):
        delete_recurring(recurring, path)
    assert len(list_occurrences(2026, 1, database_path=path)) == 1

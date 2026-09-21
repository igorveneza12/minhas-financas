from datetime import date

import pytest

from src.accounts import create_account, list_accounts
from src.budget import budget_summary, list_budget_status, upsert_budget
from src.categories import seed_default_categories
from src.credit_cards import create_card, create_purchase
from src.database import get_connection, initialize_database
from src.debts import create_debt, create_debt_payment, debt_totals
from src.goals import create_goal, goal_progress, goals_summary, list_goals
from src.transactions import create_transaction, total_balance_cents


def setup_v04(tmp_path):
    path = tmp_path / "financeiro.db"
    initialize_database(path)
    seed_default_categories(path)
    with get_connection(path) as connection:
        categories = {row["name"]: row["id"] for row in connection.execute("SELECT id, name FROM categories")}
    account = create_account("Conta 0.4", "conta_corrente", 200000, path)
    return path, account, categories


def test_budget_combines_direct_and_card_expenses(tmp_path):
    path, account, categories = setup_v04(tmp_path)
    upsert_budget(categories["Alimentação"], 2026, 10, 10000, path)
    create_transaction("Mercado", 3000, "despesa", "2026-10-01", account, categories["Alimentação"], database_path=path)
    card = create_card("Cartão", "Banco", None, 100000, 20, 10, database_path=path)
    create_purchase(card, "Compra cartão", 4000, date(2026, 9, 19), categories["Alimentação"], 1, database_path=path)
    status = list_budget_status(2026, 10, path)[0]
    assert status["spent_cents"] == 7000
    assert budget_summary(2026, 10, path)["limit_cents"] == 10000


def test_budget_can_be_over_limit_without_blocking_expenses(tmp_path):
    path, account, categories = setup_v04(tmp_path)
    upsert_budget(categories["Lazer"], 2026, 1, 1000, path)
    create_transaction("Lazer", 1500, "despesa", "2026-01-10", account, categories["Lazer"], database_path=path)
    row = list_budget_status(2026, 1, path)[0]
    assert row["spent_cents"] > row["limit_cents"]


def test_debt_payment_separates_principal_interest_and_updates_balance(tmp_path):
    path, account, _ = setup_v04(tmp_path)
    debt = create_debt("Empréstimo", "Credor", 100000, 100000, "2026-01-01", database_path=path)
    create_debt_payment(debt, account, 12000, 10000, 2000, "2026-02-01", operation_key="debt-payment-1", database_path=path)
    assert debt_totals(path)["principal_cents"] == 90000
    assert list_accounts(path)[0]["balance_cents"] == 188000
    with pytest.raises(ValueError, match="já foi registrado"):
        create_debt_payment(debt, account, 12000, 10000, 2000, "2026-02-01", operation_key="debt-payment-1", database_path=path)


def test_debt_cannot_amortize_more_than_remaining(tmp_path):
    path, account, _ = setup_v04(tmp_path)
    debt = create_debt("Dívida", "Credor", 5000, 5000, "2026-01-01", database_path=path)
    with pytest.raises(ValueError, match="supera"):
        create_debt_payment(debt, account, 6000, 6000, 0, "2026-02-01", database_path=path)


def test_goal_progress_and_monthly_need_are_planning_only(tmp_path):
    path, account, _ = setup_v04(tmp_path)
    goal = create_goal("Reserva", 120000, 45000, "2026-01-01", "2027-01-01", database_path=path)
    row = list_goals(path)[0]
    progress = goal_progress(row)
    assert progress["percent"] == 37.5
    assert progress["remaining_cents"] == 75000
    assert goals_summary(path)["reserved_cents"] == 45000
    assert total_balance_cents(path) == 200000

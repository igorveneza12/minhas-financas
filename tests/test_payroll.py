import pytest

from src.accounts import create_account
from src.categories import seed_default_categories
from src.database import get_connection, initialize_database
from src.payroll import create_manual_payroll


def test_manual_payroll_records_only_net_salary(tmp_path):
    path = tmp_path / "financeiro.db"
    initialize_database(path)
    seed_default_categories(path)
    account_id = create_account("Conta salário", "conta_corrente", 0, path)
    with get_connection(path) as connection:
        category_id = connection.execute("SELECT id FROM categories WHERE name = 'Salário'").fetchone()[0]
    slip_id = create_manual_payroll("Empresa fictícia", "09/2026", "2026-09-30", 500000, 120000, 380000, account_id, category_id, database_path=path)
    assert slip_id > 0
    with get_connection(path) as connection:
        transaction = connection.execute("SELECT amount_cents FROM transactions").fetchone()
        slip = connection.execute("SELECT gross_cents, discounts_cents, net_cents, transaction_id FROM payroll_slips").fetchone()
    assert transaction["amount_cents"] == 380000
    assert tuple(slip) == (500000, 120000, 380000, 1)


def test_manual_payroll_rejects_inconsistent_net_salary(tmp_path):
    path = tmp_path / "financeiro.db"
    initialize_database(path)
    seed_default_categories(path)
    account_id = create_account("Conta salário", "conta_corrente", 0, path)
    with get_connection(path) as connection:
        category_id = connection.execute("SELECT id FROM categories WHERE name = 'Salário'").fetchone()[0]
    with pytest.raises(ValueError, match="Salário líquido"):
        create_manual_payroll("Empresa", "09/2026", "2026-09-30", 500000, 120000, 390000, account_id, category_id, database_path=path)

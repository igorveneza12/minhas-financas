from datetime import date

import pytest

from src.accounts import create_account, list_accounts
from src.categories import seed_default_categories
from src.database import initialize_database
from src.transactions import monthly_totals, total_balance_cents
from src.transfers import create_transfer, delete_transfer, list_transfers


@pytest.fixture
def database(tmp_path):
    path = tmp_path / "transfers.db"
    initialize_database(path)
    seed_default_categories(path)
    return path


def test_internal_transfer_changes_each_account_not_total_or_income(database):
    source = create_account("Sicredi", "conta_corrente", 100_000, database)
    target = create_account("Caixa", "conta_corrente", 66, database)
    before_total = total_balance_cents(database)

    transfer_id = create_transfer(source, target, 116_343, date(2026, 7, 6), "Teste", database)

    accounts = {row["name"]: row for row in list_accounts(database)}
    assert accounts["Sicredi"]["balance_cents"] == -16_343
    assert accounts["Caixa"]["balance_cents"] == 116_409
    assert total_balance_cents(database) == before_total
    assert monthly_totals(2026, 7, database) == {"receita": 0, "despesa": 0}
    assert list_transfers(database)[0]["id"] == transfer_id


def test_transfer_validation_and_delete(database):
    source = create_account("Origem", "conta_corrente", 100_000, database)
    target = create_account("Destino", "conta_corrente", 0, database)
    with pytest.raises(ValueError):
        create_transfer(source, source, 100, "2026-01-01", database_path=database)
    with pytest.raises(ValueError):
        create_transfer(source, target, 0, "2026-01-01", database_path=database)
    with pytest.raises(ValueError):
        create_transfer(source, target, 100, "data-ruim", database_path=database)

    created = create_transfer(source, target, 100, "2026-01-01", database_path=database)
    delete_transfer(created, database)
    assert not list_transfers(database)
    assert total_balance_cents(database) == 100_000

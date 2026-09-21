from datetime import date

import pytest

from src.accounts import create_account, list_accounts
from src.categories import seed_default_categories
from src.credit_cards import (
    archive_card,
    card_future_commitments,
    create_card,
    create_payment,
    create_purchase,
    delete_card,
    delete_payment,
    invoice_period_for_purchase,
    list_cards,
    list_invoices,
    list_payments,
    list_purchases,
    reactivate_card,
    split_installments,
    update_card,
)
from src.database import get_connection, initialize_database
from src.transactions import total_balance_cents


def setup_credit_database(tmp_path):
    path = tmp_path / "financeiro.db"
    initialize_database(path)
    seed_default_categories(path)
    account_id = create_account("Conta de teste", "conta_corrente", 100000, path)
    with get_connection(path) as connection:
        category_id = connection.execute(
            "SELECT id FROM categories WHERE name = 'Alimentação'"
        ).fetchone()[0]
    card_id = create_card("Cartão teste", "Instituição fictícia", "Visa", 100000, 20, 10, database_path=path)
    return path, account_id, category_id, card_id


def test_card_can_be_created_and_edited(tmp_path):
    path, _, _, card_id = setup_credit_database(tmp_path)

    update_card(card_id, "Cartão atualizado", "Banco fictício", "Mastercard", 150000, 18, 8, database_path=path)

    card = list_cards(path)[0]
    assert card["name"] == "Cartão atualizado"
    assert card["limit_cents"] == 150000
    assert card["available_cents"] == 150000


def test_card_cycle_cannot_change_after_purchase(tmp_path):
    path, _, category_id, card_id = setup_credit_database(tmp_path)
    create_purchase(card_id, "Compra existente", 1000, date(2026, 9, 19), category_id, 1, database_path=path)

    with pytest.raises(ValueError, match="dias de fechamento"):
        update_card(card_id, "Cartão teste", "Instituição fictícia", "Visa", 100000, 19, 10, database_path=path)


def test_installments_distribute_remainder_exactly():
    amounts = split_installments(1000, 3)
    assert amounts == [334, 333, 333]
    assert sum(amounts) == 1000


def test_purchase_before_on_and_after_closing_day():
    before = invoice_period_for_purchase(date(2026, 9, 19), 20, 10)
    exact = invoice_period_for_purchase(date(2026, 9, 20), 20, 10)
    after = invoice_period_for_purchase(date(2026, 9, 21), 20, 10)

    assert before[:2] == (2026, 10)
    assert exact[:2] == (2026, 10)
    assert after[:2] == (2026, 11)
    assert before[3] == date(2026, 10, 10)
    assert after[3] == date(2026, 11, 10)


def test_purchase_in_february_adjusts_invalid_day(tmp_path):
    path, _, category_id, card_id = setup_credit_database(tmp_path)
    february_card = create_card("Cartão fevereiro", "Banco fictício", None, 100000, 31, 31, database_path=path)

    create_purchase(february_card, "Compra fevereiro", 1000, date(2026, 1, 31), category_id, 2, database_path=path)
    invoices = list_invoices(path, february_card)

    assert [invoice["due_date"] for invoice in invoices] == ["2026-02-28", "2026-03-31"]


def test_purchase_creates_one_invoice_per_installment(tmp_path):
    path, _, category_id, card_id = setup_credit_database(tmp_path)

    purchase_id = create_purchase(card_id, "Compra parcelada", 120000, date(2026, 9, 19), category_id, 6, database_path=path)
    purchases = list_purchases(path, card_id)
    invoices = list_invoices(path, card_id)

    assert purchases[0]["id"] == purchase_id
    assert purchases[0]["installment_count"] == 6
    assert len(invoices) == 6
    assert all(invoice["total_cents"] == 20000 for invoice in invoices)
    assert sum(invoice["total_cents"] for invoice in invoices) == 120000


def test_full_and_partial_payment_update_account_and_card_limit(tmp_path):
    path, account_id, category_id, card_id = setup_credit_database(tmp_path)
    create_purchase(card_id, "Compra", 30000, date(2026, 9, 19), category_id, 1, database_path=path)
    invoice = list_invoices(path, card_id)[0]

    payment_id = create_payment(invoice["id"], account_id, 10000, date(2026, 9, 25), operation_key="pagamento-1", database_path=path)
    assert payment_id > 0
    assert list_invoices(path, card_id)[0]["pending_cents"] == 20000
    assert list_cards(path)[0]["available_cents"] == 80000
    assert list_accounts(path)[0]["balance_cents"] == 90000
    assert total_balance_cents(path) == 90000

    create_payment(invoice["id"], account_id, 20000, date(2026, 9, 26), operation_key="pagamento-2", database_path=path)
    assert list_invoices(path, card_id)[0]["pending_cents"] == 0
    assert list_cards(path)[0]["unpaid_cents"] == 0
    assert len(list_payments(invoice["id"], path)) == 2


def test_payment_cannot_exceed_pending_or_duplicate_operation(tmp_path):
    path, account_id, category_id, card_id = setup_credit_database(tmp_path)
    create_purchase(card_id, "Compra", 5000, date(2026, 9, 19), category_id, 1, database_path=path)
    invoice_id = list_invoices(path, card_id)[0]["id"]

    with pytest.raises(ValueError, match="maior que o valor pendente"):
        create_payment(invoice_id, account_id, 5001, date(2026, 9, 25), operation_key="repetido", database_path=path)
    create_payment(invoice_id, account_id, 5000, date(2026, 9, 25), operation_key="repetido", database_path=path)
    with pytest.raises(ValueError, match="já foi registrado"):
        create_payment(invoice_id, account_id, 1, date(2026, 9, 25), operation_key="repetido", database_path=path)


def test_payment_reversal_only_allows_latest_payment(tmp_path):
    path, account_id, category_id, card_id = setup_credit_database(tmp_path)
    create_purchase(card_id, "Compra", 10000, date(2026, 9, 19), category_id, 1, database_path=path)
    invoice_id = list_invoices(path, card_id)[0]["id"]
    first = create_payment(invoice_id, account_id, 3000, date(2026, 9, 25), operation_key="primeiro", database_path=path)
    second = create_payment(invoice_id, account_id, 2000, date(2026, 9, 26), operation_key="segundo", database_path=path)

    with pytest.raises(ValueError, match="pagamentos posteriores"):
        delete_payment(first, path)
    delete_payment(second, path)
    assert list_invoices(path, card_id)[0]["pending_cents"] == 7000


def test_archived_card_preserves_history_and_blocks_new_purchase(tmp_path):
    path, _, category_id, card_id = setup_credit_database(tmp_path)
    create_purchase(card_id, "Histórico", 1000, date(2026, 9, 19), category_id, 1, database_path=path)
    archive_card(card_id, path)

    with pytest.raises(ValueError, match="arquivados"):
        create_purchase(card_id, "Nova compra", 1000, date(2026, 9, 20), category_id, 1, database_path=path)
    assert len(list_purchases(path, card_id)) == 1
    reactivate_card(card_id, path)
    create_purchase(card_id, "Compra após reativação", 1000, date(2026, 9, 20), category_id, 1, database_path=path)
    assert len(list_purchases(path, card_id)) == 2


def test_card_with_history_cannot_be_deleted_but_empty_card_can(tmp_path):
    path, _, category_id, card_id = setup_credit_database(tmp_path)
    empty_card = create_card("Vazio", "Banco fictício", None, 1000, 20, 10, database_path=path)
    delete_card(empty_card, path)
    assert all(card["id"] != empty_card for card in list_cards(path, include_archived=True))

    create_purchase(card_id, "Compra", 1000, date(2026, 9, 19), category_id, 1, database_path=path)
    with pytest.raises(ValueError, match="histórico"):
        delete_card(card_id, path)


def test_future_commitments_keep_empty_months_out_of_business_result(tmp_path):
    path, _, category_id, card_id = setup_credit_database(tmp_path)
    create_purchase(card_id, "Compra futura", 1000, date(2026, 9, 19), category_id, 2, database_path=path)

    commitments = card_future_commitments(path)
    assert len(commitments) == 2
    assert all(row["total_cents"] == 500 for row in commitments)

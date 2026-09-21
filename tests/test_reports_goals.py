"""Novos testes: metas e relatórios, todos em bancos SQLite temporários."""
from datetime import date
import csv
import io

import pytest
from openpyxl import load_workbook

from src.accounts import create_account
from src.categories import seed_default_categories
from src.credit_cards import create_card, create_purchase, create_payment, list_invoices
from src.database import initialize_database, get_connection
from src.goals import archive_goal, create_goal, delete_goal, list_goals, reactivate_goal, goals_summary
from src.reports import period_report, report_csv, report_excel
from src.transactions import create_transaction, total_balance_cents


def fixture_db(tmp_path):
    path = tmp_path / "financeiro.db"
    initialize_database(path)
    seed_default_categories(path)
    with get_connection(path) as conn:
        categories = {row["name"]: row["id"] for row in conn.execute("SELECT name, id FROM categories")}
    account = create_account("Alfa", "conta_corrente", 250000, path)
    return path, account, categories


def test_goal_delete_and_archive_keep_balance(tmp_path):
    path, account, _ = fixture_db(tmp_path)
    empty = create_goal("Teste vazio", 100000, 0, "2026-09-01", database_path=path)
    reserved = create_goal("Reserva", 1200000, 100000, "2026-09-01", database_path=path)
    with pytest.raises(ValueError, match="reservado"):
        delete_goal(reserved, path)
    assert len(list_goals(path)) == 2
    delete_goal(empty, path)
    assert [r["id"] for r in list_goals(path)] == [reserved]
    archive_goal(reserved, path)
    assert list_goals(path) == []
    assert goals_summary(path)["reserved_cents"] == 0
    reactivate_goal(reserved, path)
    assert goals_summary(path)["reserved_cents"] == 100000
    assert total_balance_cents(path) == 250000
    with pytest.raises(ValueError, match="não encontrada"):
        delete_goal(empty, path)


def test_report_card_uses_due_date_without_double_counting_payment(tmp_path):
    path, account, cat = fixture_db(tmp_path)
    create_transaction("Salário", 450000, "receita", "2026-09-05", account, cat["Salário"], database_path=path)
    create_transaction("Mercado", 45000, "despesa", "2026-09-07", account, cat["Alimentação"], database_path=path)
    card = create_card("Cartão", "Banco", None, 500000, 20, 10, database_path=path)
    create_purchase(card, "Micro-ondas", 120000, date(2026, 9, 19), cat["Compras"], 6, database_path=path)
    september = period_report(date(2026,9,1), date(2026,9,30), path)
    assert (september["revenue_cents"], september["expense_cents"]) == (450000, 45000)
    october = period_report(date(2026,10,1), date(2026,10,31), path)
    assert october["expense_cents"] == 20000
    assert october["categories"] == {"Compras": 20000}
    invoice = list_invoices(path)[0]
    create_payment(invoice["id"], account, 20000, "2026-10-10", database_path=path)
    october_after = period_report(date(2026,10,1), date(2026,10,31), path)
    assert october_after["expense_cents"] == 20000
    assert total_balance_cents(path) == 250000 + 450000 - 45000 - 20000
    filtered = period_report(date(2026,10,1), date(2026,10,31), path, account_id=account)
    assert filtered["expense_cents"] == 0
    filtered_category = period_report(date(2026,10,1), date(2026,10,31), path, category_id=cat["Compras"])
    assert filtered_category["expense_cents"] == 20000


def test_reports_export_data_and_block_formulas(tmp_path):
    path, account, categories = fixture_db(tmp_path)
    create_transaction("=HYPERLINK(\"x\")", 1234, "despesa", "2026-09-02", account, categories["Compras"], database_path=path)
    rows = period_report(date(2026,9,1), date(2026,9,30), path)["entries"]
    content = report_csv(rows).decode("utf-8-sig")
    values = list(csv.reader(io.StringIO(content), delimiter=";"))
    assert values[1][2].startswith("'=")
    assert values[1][-1] == "12,34"
    wb = load_workbook(io.BytesIO(report_excel(rows)))
    sheet = wb.active
    assert sheet["C2"].data_type == "s"
    assert sheet["G2"].value == 12.34
    assert sheet["G2"].number_format.startswith('"R$ "')
    with pytest.raises(ValueError, match="data inicial"):
        period_report(date(2026,10,1), date(2026,9,1), path)

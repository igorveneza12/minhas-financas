"""Consultas de relatórios: despesas por competência, sem duplicar pagamentos."""

from datetime import date
from pathlib import Path
import csv
import io

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

from .database import DEFAULT_DATABASE_PATH, get_connection


def _check_period(start: date, end: date) -> tuple[str, str]:
    if start > end:
        raise ValueError("A data inicial deve ser anterior ou igual à data final.")
    return start.isoformat(), end.isoformat()


def period_report(
    start: date,
    end: date,
    database_path: str | Path = DEFAULT_DATABASE_PATH,
    account_id: int | None = None,
    category_id: int | None = None,
) -> dict:
    """Retorna lançamentos diretos e parcelas de cartão por data de vencimento.

    Quando uma conta é filtrada, omite parcelas do cartão: compras de crédito não
    pertencem a uma conta bancária antes de pagar a fatura.
    """
    begin, finish = _check_period(start, end)
    with get_connection(database_path) as conn:
        direct_sql = """
            SELECT t.transaction_date AS date, t.description, t.transaction_type AS type,
                   t.amount_cents, c.name AS category, a.name AS account,
                   'Movimentação' AS origin
            FROM transactions t JOIN categories c ON c.id = t.category_id
            JOIN accounts a ON a.id = t.account_id
            WHERE t.transaction_date BETWEEN ? AND ?
        """
        params: list = [begin, finish]
        if account_id is not None:
            direct_sql += " AND t.account_id = ?"
            params.append(account_id)
        if category_id is not None:
            direct_sql += " AND t.category_id = ?"
            params.append(category_id)
        direct_sql += " ORDER BY t.transaction_date, t.id"
        direct = [dict(row) for row in conn.execute(direct_sql, params)]

        card: list[dict] = []
        if account_id is None:
            card_sql = """
                SELECT inv.due_date AS date, p.description, 'despesa' AS type,
                       i.amount_cents, cat.name AS category, cc.name AS account,
                       'Parcela de cartão' AS origin
                FROM card_installments i
                JOIN card_invoices inv ON inv.id = i.invoice_id
                JOIN card_purchases p ON p.id = i.purchase_id
                JOIN credit_cards cc ON cc.id = p.card_id
                JOIN categories cat ON cat.id = p.category_id
                WHERE p.status = 'active' AND inv.due_date BETWEEN ? AND ?
            """
            card_params: list = [begin, finish]
            if category_id is not None:
                card_sql += " AND p.category_id = ?"
                card_params.append(category_id)
            card_sql += " ORDER BY inv.due_date, i.id"
            card = [dict(row) for row in conn.execute(card_sql, card_params)]

    entries = sorted(direct + card, key=lambda row: (row["date"], row["description"]))
    revenue = sum(r["amount_cents"] for r in entries if r["type"] == "receita")
    expense = sum(r["amount_cents"] for r in entries if r["type"] == "despesa")
    categories: dict[str, int] = {}
    for row in entries:
        if row["type"] == "despesa":
            categories[row["category"]] = categories.get(row["category"], 0) + row["amount_cents"]
    return {"entries": entries, "revenue_cents": revenue, "expense_cents": expense,
            "result_cents": revenue - expense, "categories": categories}


FIELDS = (("date", "Data"), ("type", "Tipo"), ("description", "Descrição"),
          ("category", "Categoria"), ("account", "Conta ou cartão"),
          ("origin", "Origem"), ("amount_cents", "Valor (R$)"))


def _text_for_spreadsheet(value: object) -> str:
    """Evita que descrições importadas sejam interpretadas como fórmulas."""
    text = str(value)
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) else text


def report_csv(entries: list[dict]) -> bytes:
    result = io.StringIO(newline="")
    writer = csv.writer(result, delimiter=";")
    writer.writerow([label for _, label in FIELDS])
    for entry in entries:
        writer.writerow([f"{entry[key] / 100:.2f}".replace(".", ",") if key == "amount_cents"
                         else _text_for_spreadsheet(entry[key]) for key, _ in FIELDS])
    return ("\ufeff" + result.getvalue()).encode("utf-8")


def report_excel(entries: list[dict]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Movimentações"
    ws.append([label for _, label in FIELDS])
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:G{max(2, len(entries) + 1)}"
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1B4965")
    for entry in entries:
        ws.append([entry[key] / 100 if key == "amount_cents"
                   else _text_for_spreadsheet(entry[key]) for key, _ in FIELDS])
        ws.cell(ws.max_row, 7).number_format = '"R$ "#,##0.00;[Red]("R$ "#,##0.00)'
    for col, width in {"A": 15, "B": 13, "C": 43, "D": 23, "E": 28, "F": 23, "G": 18}.items():
        ws.column_dimensions[col].width = width
    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()

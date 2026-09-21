from calendar import monthrange
from datetime import date
from pathlib import Path
import sqlite3
from typing import Iterable

from .accounts import money_to_cents
from .database import DEFAULT_DATABASE_PATH, get_connection


MAX_INSTALLMENTS = 120


def _last_day(year: int, month: int) -> int:
    return monthrange(year, month)[1]


def _safe_date(year: int, month: int, day: int) -> date:
    return date(year, month, min(day, _last_day(year, month)))


def _add_months(year: int, month: int, months: int) -> tuple[int, int]:
    index = year * 12 + month - 1 + months
    return index // 12, index % 12 + 1


def invoice_period_for_purchase(
    purchase_date: date,
    closing_day: int,
    due_day: int,
) -> tuple[int, int, date, date]:
    """Calcula a fatura inicial; compra no fechamento entra no ciclo encerrado nesse dia."""
    offset = 1 if purchase_date.day <= closing_day else 2
    due_year, due_month = _add_months(purchase_date.year, purchase_date.month, offset)
    due_date = _safe_date(due_year, due_month, due_day)
    closing_year, closing_month = _add_months(due_year, due_month, -1)
    closing_date = _safe_date(closing_year, closing_month, closing_day)
    return due_year, due_month, closing_date, due_date


def split_installments(total_cents: int, count: int) -> list[int]:
    if total_cents <= 0:
        raise ValueError("O valor total deve ser maior que zero.")
    if count < 1 or count > MAX_INSTALLMENTS:
        raise ValueError(f"O número de parcelas deve estar entre 1 e {MAX_INSTALLMENTS}.")
    base, remainder = divmod(total_cents, count)
    return [base + (1 if index < remainder else 0) for index in range(count)]


def _validate_card_days(closing_day: int, due_day: int) -> None:
    if not 1 <= closing_day <= 31 or not 1 <= due_day <= 31:
        raise ValueError("Os dias de fechamento e vencimento devem estar entre 1 e 31.")


def create_card(
    name: str,
    institution: str,
    brand: str | None,
    limit_cents: int,
    closing_day: int,
    due_day: int,
    color: str | None = None,
    database_path: str | Path = DEFAULT_DATABASE_PATH,
) -> int:
    if not name.strip() or not institution.strip():
        raise ValueError("Nome e instituição são obrigatórios.")
    if not isinstance(limit_cents, int) or isinstance(limit_cents, bool) or limit_cents < 0:
        raise ValueError("O limite deve ser informado em centavos e não pode ser negativo.")
    _validate_card_days(closing_day, due_day)
    with get_connection(database_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO credit_cards
                (name, institution, brand, limit_cents, closing_day, due_day, color)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (name.strip(), institution.strip(), (brand or "").strip(), limit_cents, closing_day, due_day, color),
        )
        return int(cursor.lastrowid)


def update_card(
    card_id: int,
    name: str,
    institution: str,
    brand: str | None,
    limit_cents: int,
    closing_day: int,
    due_day: int,
    color: str | None = None,
    database_path: str | Path = DEFAULT_DATABASE_PATH,
) -> None:
    if not name.strip() or not institution.strip():
        raise ValueError("Nome e instituição são obrigatórios.")
    if not isinstance(limit_cents, int) or isinstance(limit_cents, bool) or limit_cents < 0:
        raise ValueError("O limite deve ser informado em centavos e não pode ser negativo.")
    _validate_card_days(closing_day, due_day)
    with get_connection(database_path) as connection:
        existing = _card_row(connection, card_id)
        has_purchases = connection.execute(
            "SELECT EXISTS(SELECT 1 FROM card_purchases WHERE card_id = ?)", (card_id,)
        ).fetchone()[0]
        if has_purchases and (
            existing["closing_day"] != closing_day or existing["due_day"] != due_day
        ):
            raise ValueError(
                "Os dias de fechamento e vencimento não podem ser alterados após registrar compras."
            )
        cursor = connection.execute(
            """
            UPDATE credit_cards
            SET name = ?, institution = ?, brand = ?, limit_cents = ?, closing_day = ?, due_day = ?, color = ?
            WHERE id = ?
            """,
            (name.strip(), institution.strip(), (brand or "").strip(), limit_cents, closing_day, due_day, color, card_id),
        )
        if cursor.rowcount != 1:
            raise ValueError("Cartão não encontrado.")


def _card_row(connection: sqlite3.Connection, card_id: int) -> sqlite3.Row:
    row = connection.execute("SELECT * FROM credit_cards WHERE id = ?", (card_id,)).fetchone()
    if row is None:
        raise ValueError("Cartão não encontrado.")
    return row


def _invoice_totals(connection: sqlite3.Connection, invoice_id: int) -> tuple[int, int]:
    total = connection.execute(
        "SELECT COALESCE(SUM(amount_cents), 0) FROM card_installments WHERE invoice_id = ?",
        (invoice_id,),
    ).fetchone()[0]
    paid = connection.execute(
        "SELECT COALESCE(SUM(amount_cents), 0) FROM card_payments WHERE invoice_id = ?",
        (invoice_id,),
    ).fetchone()[0]
    return int(total), int(paid)


def list_cards(
    database_path: str | Path = DEFAULT_DATABASE_PATH,
    include_archived: bool = False,
) -> list[sqlite3.Row]:
    active_filter = "" if include_archived else "WHERE c.active = 1"
    with get_connection(database_path) as connection:
        rows = connection.execute(
            f"""
            SELECT c.*, COALESCE((
                SELECT SUM(i.amount_cents)
                FROM card_installments AS i
                JOIN card_invoices AS inv ON inv.id = i.invoice_id
                LEFT JOIN card_payments AS p ON p.invoice_id = inv.id
                WHERE i.purchase_id IN (SELECT id FROM card_purchases WHERE card_id = c.id AND status = 'active')
            ), 0) AS installment_total_cents
            FROM credit_cards AS c
            {active_filter}
            ORDER BY c.name COLLATE NOCASE
            """
        ).fetchall()
        result = []
        today = date.today()
        for row in rows:
            invoices = connection.execute(
                "SELECT id, due_date FROM card_invoices WHERE card_id = ? ORDER BY due_date",
                (row["id"],),
            ).fetchall()
            unpaid = 0
            current_invoice = 0
            next_due = None
            for invoice in invoices:
                total, paid = _invoice_totals(connection, invoice["id"])
                pending = max(total - paid, 0)
                unpaid += pending
                due = date.fromisoformat(invoice["due_date"])
                if pending and next_due is None and due >= today:
                    next_due = invoice["due_date"]
                    current_invoice = pending
            result.append({**dict(row), "unpaid_cents": unpaid, "available_cents": row["limit_cents"] - unpaid, "current_invoice_cents": current_invoice, "next_due_date": next_due})
        return result


def _ensure_invoice(
    connection: sqlite3.Connection,
    card_id: int,
    billing_year: int,
    billing_month: int,
    closing_date: date,
    due_date: date,
) -> int:
    connection.execute(
        """
        INSERT OR IGNORE INTO card_invoices
            (card_id, billing_year, billing_month, closing_date, due_date)
        VALUES (?, ?, ?, ?, ?)
        """,
        (card_id, billing_year, billing_month, closing_date.isoformat(), due_date.isoformat()),
    )
    return int(connection.execute(
        "SELECT id FROM card_invoices WHERE card_id = ? AND billing_year = ? AND billing_month = ?",
        (card_id, billing_year, billing_month),
    ).fetchone()[0])


def _insert_installments(
    connection: sqlite3.Connection,
    purchase_id: int,
    card: sqlite3.Row,
    purchase_date: date,
    amounts: Iterable[int],
) -> None:
    first_year, first_month, _, _ = invoice_period_for_purchase(
        purchase_date, card["closing_day"], card["due_day"]
    )
    for number, amount in enumerate(amounts, start=1):
        year, month = _add_months(first_year, first_month, number - 1)
        closing_year, closing_month = _add_months(year, month, -1)
        closing_date = _safe_date(closing_year, closing_month, card["closing_day"])
        due_date = _safe_date(year, month, card["due_day"])
        invoice_id = _ensure_invoice(connection, card["id"], year, month, closing_date, due_date)
        connection.execute(
            """
            INSERT INTO card_installments
                (purchase_id, invoice_id, installment_number, amount_cents)
            VALUES (?, ?, ?, ?)
            """,
            (purchase_id, invoice_id, number, amount),
        )


def create_purchase(
    card_id: int,
    description: str,
    total_amount_cents: int,
    purchase_date: str | date,
    category_id: int,
    installments_count: int = 1,
    notes: str = "",
    database_path: str | Path = DEFAULT_DATABASE_PATH,
) -> int:
    if not description.strip():
        raise ValueError("A descrição da compra é obrigatória.")
    if not isinstance(total_amount_cents, int) or total_amount_cents <= 0:
        raise ValueError("O valor da compra deve ser maior que zero.")
    purchase_day = date.fromisoformat(purchase_date) if isinstance(purchase_date, str) else purchase_date
    amounts = split_installments(total_amount_cents, installments_count)
    with get_connection(database_path) as connection:
        card = _card_row(connection, card_id)
        if not card["active"]:
            raise ValueError("Cartões arquivados não podem receber novas compras.")
        category = connection.execute(
            "SELECT id FROM categories WHERE id = ? AND category_type = 'despesa' AND active = 1",
            (category_id,),
        ).fetchone()
        if category is None:
            raise ValueError("A categoria de despesa selecionada não é válida.")
        cursor = connection.execute(
            """
            INSERT INTO card_purchases
                (card_id, category_id, description, total_amount_cents, purchase_date, installments_count, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (card_id, category_id, description.strip(), total_amount_cents, purchase_day.isoformat(), installments_count, notes.strip()),
        )
        purchase_id = int(cursor.lastrowid)
        _insert_installments(connection, purchase_id, card, purchase_day, amounts)
        return purchase_id


def _purchase_has_payments(connection: sqlite3.Connection, purchase_id: int) -> bool:
    return connection.execute(
        """
        SELECT EXISTS(
            SELECT 1 FROM card_payments AS p
            JOIN card_installments AS i ON i.invoice_id = p.invoice_id
            WHERE i.purchase_id = ?
        )
        """,
        (purchase_id,),
    ).fetchone()[0] == 1


def update_purchase(
    purchase_id: int,
    description: str,
    total_amount_cents: int,
    purchase_date: str | date,
    category_id: int,
    installments_count: int,
    notes: str = "",
    database_path: str | Path = DEFAULT_DATABASE_PATH,
) -> None:
    if not description.strip():
        raise ValueError("A descrição da compra é obrigatória.")
    purchase_day = date.fromisoformat(purchase_date) if isinstance(purchase_date, str) else purchase_date
    amounts = split_installments(total_amount_cents, installments_count)
    with get_connection(database_path) as connection:
        purchase = connection.execute("SELECT * FROM card_purchases WHERE id = ?", (purchase_id,)).fetchone()
        if purchase is None or purchase["status"] != "active":
            raise ValueError("Compra ativa não encontrada.")
        if _purchase_has_payments(connection, purchase_id):
            raise ValueError("A compra não pode ser alterada porque já existe pagamento vinculado.")
        category = connection.execute(
            "SELECT id FROM categories WHERE id = ? AND category_type = 'despesa' AND active = 1",
            (category_id,),
        ).fetchone()
        if category is None:
            raise ValueError("A categoria de despesa selecionada não é válida.")
        card = _card_row(connection, purchase["card_id"])
        connection.execute(
            """
            UPDATE card_purchases
            SET description = ?, total_amount_cents = ?, purchase_date = ?, category_id = ?, installments_count = ?, notes = ?
            WHERE id = ?
            """,
            (description.strip(), total_amount_cents, purchase_day.isoformat(), category_id, installments_count, notes.strip(), purchase_id),
        )
        connection.execute("DELETE FROM card_installments WHERE purchase_id = ?", (purchase_id,))
        _insert_installments(connection, purchase_id, card, purchase_day, amounts)


def cancel_purchase(purchase_id: int, database_path: str | Path = DEFAULT_DATABASE_PATH) -> None:
    with get_connection(database_path) as connection:
        if _purchase_has_payments(connection, purchase_id):
            raise ValueError("A compra não pode ser cancelada porque já existe pagamento vinculado.")
        cursor = connection.execute(
            "UPDATE card_purchases SET status = 'canceled' WHERE id = ? AND status = 'active'",
            (purchase_id,),
        )
        if cursor.rowcount != 1:
            raise ValueError("Compra ativa não encontrada.")
        connection.execute("DELETE FROM card_installments WHERE purchase_id = ?", (purchase_id,))


def list_purchases(database_path: str | Path = DEFAULT_DATABASE_PATH, card_id: int | None = None) -> list[sqlite3.Row]:
    query = """
        SELECT p.*, c.name AS card_name, cat.name AS category_name,
               COALESCE(SUM(i.amount_cents), 0) AS installment_sum_cents,
               COUNT(i.id) AS installment_count
        FROM card_purchases AS p
        JOIN credit_cards AS c ON c.id = p.card_id
        JOIN categories AS cat ON cat.id = p.category_id
        LEFT JOIN card_installments AS i ON i.purchase_id = p.id
        WHERE p.status = 'active'
    """
    parameters: list[object] = []
    if card_id is not None:
        query += " AND p.card_id = ?"
        parameters.append(card_id)
    query += " GROUP BY p.id ORDER BY p.purchase_date DESC, p.id DESC"
    with get_connection(database_path) as connection:
        return connection.execute(query, parameters).fetchall()


def purchase_installments(purchase_id: int, database_path: str | Path = DEFAULT_DATABASE_PATH) -> list[sqlite3.Row]:
    with get_connection(database_path) as connection:
        return connection.execute(
            """
            SELECT i.*, inv.due_date,
                   COALESCE((SELECT SUM(amount_cents) FROM card_payments WHERE invoice_id = i.invoice_id), 0) AS invoice_paid_cents
            FROM card_installments AS i
            JOIN card_invoices AS inv ON inv.id = i.invoice_id
            WHERE i.purchase_id = ?
            ORDER BY i.installment_number
            """,
            (purchase_id,),
        ).fetchall()


def invoice_status(total_cents: int, paid_cents: int, due_date: date, closing_date: date, as_of: date | None = None) -> str:
    today = as_of or date.today()
    pending = total_cents - paid_cents
    if total_cents == 0:
        return "Sem compras"
    if pending <= 0:
        return "Paga"
    if due_date < today:
        return "Vencida"
    if closing_date < today:
        return "Fechada"
    return "Aberta"


def list_invoices(
    database_path: str | Path = DEFAULT_DATABASE_PATH,
    card_id: int | None = None,
) -> list[dict[str, object]]:
    query = "SELECT * FROM card_invoices"
    parameters: list[object] = []
    if card_id is not None:
        query += " WHERE card_id = ?"
        parameters.append(card_id)
    query += " ORDER BY due_date"
    with get_connection(database_path) as connection:
        result = []
        for invoice in connection.execute(query, parameters).fetchall():
            total, paid = _invoice_totals(connection, invoice["id"])
            result.append({**dict(invoice), "total_cents": total, "paid_cents": paid, "pending_cents": max(total - paid, 0), "status": invoice_status(total, paid, date.fromisoformat(invoice["due_date"]), date.fromisoformat(invoice["closing_date"]))})
        return result


def invoice_installments(invoice_id: int, database_path: str | Path = DEFAULT_DATABASE_PATH) -> list[sqlite3.Row]:
    with get_connection(database_path) as connection:
        return connection.execute(
            """
            SELECT i.*, p.description, p.purchase_date, c.name AS category_name
            FROM card_installments AS i
            JOIN card_purchases AS p ON p.id = i.purchase_id
            JOIN categories AS c ON c.id = p.category_id
            WHERE i.invoice_id = ?
            ORDER BY i.installment_number
            """,
            (invoice_id,),
        ).fetchall()


def archive_card(card_id: int, database_path: str | Path = DEFAULT_DATABASE_PATH) -> None:
    with get_connection(database_path) as connection:
        cursor = connection.execute("UPDATE credit_cards SET active = 0 WHERE id = ? AND active = 1", (card_id,))
        if cursor.rowcount != 1:
            raise ValueError("Cartão ativo não encontrado.")


def reactivate_card(card_id: int, database_path: str | Path = DEFAULT_DATABASE_PATH) -> None:
    with get_connection(database_path) as connection:
        cursor = connection.execute("UPDATE credit_cards SET active = 1 WHERE id = ? AND active = 0", (card_id,))
        if cursor.rowcount != 1:
            raise ValueError("Cartão arquivado não encontrado.")


def delete_card(card_id: int, database_path: str | Path = DEFAULT_DATABASE_PATH) -> None:
    with get_connection(database_path) as connection:
        _card_row(connection, card_id)
        linked = connection.execute(
            """
            SELECT EXISTS(SELECT 1 FROM card_purchases WHERE card_id = ?)
                OR EXISTS(SELECT 1 FROM card_invoices WHERE card_id = ?)
            """,
            (card_id, card_id),
        ).fetchone()[0]
        if linked:
            raise ValueError("O cartão possui histórico de compras ou faturas e não pode ser excluído. Arquive-o.")
        connection.execute("DELETE FROM credit_cards WHERE id = ?", (card_id,))


def create_payment(
    invoice_id: int,
    account_id: int,
    amount_cents: int,
    payment_date: str | date,
    notes: str = "",
    operation_key: str | None = None,
    database_path: str | Path = DEFAULT_DATABASE_PATH,
) -> int:
    if amount_cents <= 0:
        raise ValueError("O pagamento deve ser maior que zero.")
    payment_day = date.fromisoformat(payment_date) if isinstance(payment_date, str) else payment_date
    key = operation_key or f"invoice-{invoice_id}-account-{account_id}-{payment_day.isoformat()}-{amount_cents}"
    with get_connection(database_path) as connection:
        invoice = connection.execute("SELECT id FROM card_invoices WHERE id = ?", (invoice_id,)).fetchone()
        account = connection.execute("SELECT id FROM accounts WHERE id = ? AND active = 1", (account_id,)).fetchone()
        if invoice is None:
            raise ValueError("Fatura não encontrada.")
        if account is None:
            raise ValueError("A conta selecionada está arquivada ou não existe.")
        if connection.execute(
            "SELECT 1 FROM card_payments WHERE operation_key = ?", (key,)
        ).fetchone() is not None:
            raise ValueError("Este pagamento já foi registrado.")
        total, paid = _invoice_totals(connection, invoice_id)
        if amount_cents > total - paid:
            raise ValueError("O pagamento não pode ser maior que o valor pendente da fatura.")
        try:
            cursor = connection.execute(
                """
                INSERT INTO card_payments
                    (invoice_id, account_id, amount_cents, payment_date, notes, operation_key)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (invoice_id, account_id, amount_cents, payment_day.isoformat(), notes.strip(), key),
            )
        except sqlite3.IntegrityError as error:
            if "operation_key" in str(error):
                raise ValueError("Este pagamento já foi registrado.") from error
            raise
        return int(cursor.lastrowid)


def delete_payment(payment_id: int, database_path: str | Path = DEFAULT_DATABASE_PATH) -> None:
    with get_connection(database_path) as connection:
        payment = connection.execute("SELECT * FROM card_payments WHERE id = ?", (payment_id,)).fetchone()
        if payment is None:
            raise ValueError("Pagamento não encontrado.")
        later = connection.execute(
            """
            SELECT EXISTS(
                SELECT 1 FROM card_payments
                WHERE invoice_id = ? AND (payment_date > ? OR (payment_date = ? AND id > ?))
            )
            """,
            (payment["invoice_id"], payment["payment_date"], payment["payment_date"], payment_id),
        ).fetchone()[0]
        if later:
            raise ValueError("O pagamento não pode ser revertido porque existem pagamentos posteriores.")
        connection.execute("DELETE FROM card_payments WHERE id = ?", (payment_id,))


def list_payments(invoice_id: int, database_path: str | Path = DEFAULT_DATABASE_PATH) -> list[sqlite3.Row]:
    with get_connection(database_path) as connection:
        return connection.execute(
            """
            SELECT p.*, a.name AS account_name
            FROM card_payments AS p
            JOIN accounts AS a ON a.id = p.account_id
            WHERE p.invoice_id = ?
            ORDER BY p.payment_date DESC, p.id DESC
            """,
            (invoice_id,),
        ).fetchall()


def card_future_commitments(database_path: str | Path = DEFAULT_DATABASE_PATH) -> list[sqlite3.Row]:
    with get_connection(database_path) as connection:
        return connection.execute(
            """
            SELECT inv.due_date, c.name AS card_name, SUM(i.amount_cents) AS total_cents
            FROM card_installments AS i
            JOIN card_invoices AS inv ON inv.id = i.invoice_id
            JOIN credit_cards AS c ON c.id = inv.card_id
            JOIN card_purchases AS p ON p.id = i.purchase_id
            WHERE p.status = 'active' AND inv.due_date >= date('now')
            GROUP BY inv.id
            ORDER BY inv.due_date
            """
        ).fetchall()


def monthly_card_totals(
    year: int,
    month: int,
    database_path: str | Path = DEFAULT_DATABASE_PATH,
) -> dict[str, int]:
    with get_connection(database_path) as connection:
        row = connection.execute(
            """
            SELECT COALESCE(SUM(i.amount_cents), 0) AS total
            FROM card_installments AS i
            JOIN card_invoices AS inv ON inv.id = i.invoice_id
            JOIN card_purchases AS p ON p.id = i.purchase_id
            WHERE p.status = 'active'
              AND strftime('%Y-%m', inv.due_date) = ?
            """,
            (f"{year:04d}-{month:02d}",),
        ).fetchone()
        return {"despesa_cartao": int(row["total"])}


def monthly_card_expenses_by_category(
    year: int,
    month: int,
    database_path: str | Path = DEFAULT_DATABASE_PATH,
) -> list[sqlite3.Row]:
    with get_connection(database_path) as connection:
        return connection.execute(
            """
            SELECT cat.name AS category_name, SUM(i.amount_cents) AS total_cents
            FROM card_installments AS i
            JOIN card_invoices AS inv ON inv.id = i.invoice_id
            JOIN card_purchases AS p ON p.id = i.purchase_id
            JOIN categories AS cat ON cat.id = p.category_id
            WHERE p.status = 'active'
              AND strftime('%Y-%m', inv.due_date) = ?
            GROUP BY cat.id
            ORDER BY total_cents DESC
            """,
            (f"{year:04d}-{month:02d}",),
        ).fetchall()


def unpaid_invoices_total(database_path: str | Path = DEFAULT_DATABASE_PATH) -> int:
    return sum(int(invoice["pending_cents"]) for invoice in list_invoices(database_path))


def upcoming_invoices_total(
    database_path: str | Path = DEFAULT_DATABASE_PATH,
    limit: int = 3,
) -> int:
    return sum(
        int(row["total_cents"])
        for row in card_future_commitments(database_path)[:limit]
    )

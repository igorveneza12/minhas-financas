from io import BytesIO

import pandas as pd
import pytest

from src.accounts import create_account, list_accounts
from src.categories import seed_default_categories
from src.database import get_connection, initialize_database
from src.importers import ImportRecord, document_hash, import_records, mark_duplicates, parse_csv, parse_dataframe, parse_money, parse_ofx, parse_pdf


def setup_import_database(tmp_path):
    path = tmp_path / "financeiro.db"
    initialize_database(path)
    seed_default_categories(path)
    account_id = create_account("Conta importação", "conta_corrente", 100000, path)
    with get_connection(path) as connection:
        category_ids = {r["name"]: r["id"] for r in connection.execute("SELECT id, name FROM categories")}
    return path, account_id, category_ids


def test_csv_and_decimal_parsing():
    data = "data;descrição;valor\n21/09/2026;Supermercado;R$ 1.234,56\n22/09/2026;Salário;5000,00\n".encode()
    _, records = parse_csv(data, ";")
    assert records[0].amount_cents == 123456
    assert records[0].transaction_date == "2026-09-21"
    assert records[0].category_name == "Alimentação"
    assert parse_money("1.234,56") == 123456


def test_excel_dataframe_import_and_missing_fields():
    dataframe = pd.DataFrame({"Data": ["2026-09-01"], "Descrição": ["Operação"], "Valor": ["10,50"]})
    records = parse_dataframe(dataframe, {"date": "Data", "description": "Descrição", "amount": "Valor"})
    assert records[0].amount_cents == 1050
    assert records[0].status == "Revisão necessária"
    assert "tipo não identificado" in records[0].issue


def test_pdf_text_extraction():
    fitz = pytest.importorskip("fitz")
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "21/09/2026 Supermercado R$ 123,45")
    _, records = parse_pdf(document.tobytes())
    assert records
    assert records[0].amount_cents == 12345


def test_ofx_extraction():
    ofx = b'''OFXHEADER:100\nDATA:OFXSGML\nVERSION:102\n\n<OFX><SIGNONMSGSRSV1><SONRS><STATUS><CODE>0</CODE></STATUS></SONRS></SIGNONMSGSRSV1><BANKMSGSRSV1><STMTTRNRS><STMTRS><BANKTRANLIST><STMTTRN><TRNTYPE>DEBIT</TRNTYPE><DTPOSTED>20260921120000</DTPOSTED><TRNAMT>-25.50</TRNAMT><FITID>abc-1</FITID><NAME>Mercado</NAME></STMTTRN></BANKTRANLIST></STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>'''
    _, records = parse_ofx(ofx)
    assert records[0].external_id == "abc-1"
    assert records[0].amount_cents == 2550
    assert records[0].transaction_type == "despesa"


def test_import_requires_confirmation_at_service_boundary_and_persists(tmp_path):
    path, account_id, categories = setup_import_database(tmp_path)
    records = [ImportRecord("2026-09-21", "Supermercado", 2500, "despesa", category_name="Alimentação", status="Pronto")]
    imported = import_records(records, account_id, categories, document_hash(b"doc"), path)
    assert imported == 1
    with get_connection(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM import_batches").fetchone()[0] == 1
    with pytest.raises(ValueError, match="já foi importado"):
        import_records(records, account_id, categories, document_hash(b"doc"), path)


def test_duplicate_detection_does_not_delete_similar_operations(tmp_path):
    path, account_id, categories = setup_import_database(tmp_path)
    records = [ImportRecord("2026-09-21", "Mercado", 1000, "despesa", category_name="Alimentação", status="Pronto")]
    import_records(records, account_id, categories, document_hash(b"first"), path)
    candidates = [ImportRecord("2026-09-21", "Mercado", 1000, "despesa", category_name="Alimentação", status="Pronto"), ImportRecord("2026-09-21", "Mercado", 1000, "despesa", category_name="Alimentação", status="Pronto")]
    mark_duplicates(candidates, account_id, path)
    assert all(candidate.is_duplicate for candidate in candidates)
    assert len(list_accounts(path)) == 1

from pathlib import Path
import sqlite3

import pandas as pd
import streamlit as st

from src.accounts import cents_to_brl, list_accounts, money_to_cents
from src.categories import list_categories
from src.database import DEFAULT_DATABASE_PATH
from src.importers import ImportRecord, document_hash, import_records, mark_duplicates, parse_csv, parse_excel, parse_ofx, parse_pdf, SUPPORTED_SUFFIXES
from src.payroll import create_manual_payroll


MAX_FILE_SIZE = 10 * 1024 * 1024
st.header("Importar documentos")
st.caption("O processamento é local. Nenhum documento é enviado para serviços externos.")
file_type = st.selectbox("Tipo de documento", ["Identificação automática", "Extrato bancário", "Holerite", "Fatura de cartão", "Comprovante de pagamento", "Planilha financeira", "Outro"])
upload = st.file_uploader("Selecione um documento", type=[suffix[1:] for suffix in SUPPORTED_SUFFIXES])
accounts = list_accounts(DEFAULT_DATABASE_PATH)
if not accounts:
    st.warning("Cadastre uma conta financeira ativa antes de importar movimentações.")

if file_type == "Holerite" and accounts:
    st.subheader("Preenchimento manual do holerite")
    st.caption("O sistema registra somente o salário líquido como receita. O bruto e os descontos ficam no demonstrativo.")
    revenue_categories = list_categories("receita", DEFAULT_DATABASE_PATH)
    with st.form("manual_payroll_form", clear_on_submit=True):
        employer = st.text_input("Empregador")
        competence = st.text_input("Competência", placeholder="Ex.: 09/2026")
        payment_date = st.date_input("Data de pagamento")
        gross = st.text_input("Salário bruto")
        discounts = st.text_input("Total de descontos", value="0,00")
        net = st.text_input("Salário líquido")
        account_name = st.selectbox("Conta de recebimento", [account["name"] for account in accounts])
        category_name = st.selectbox("Categoria de receita", [category["name"] for category in revenue_categories])
        notes = st.text_area("Observações")
        payroll_submitted = st.form_submit_button("Registrar holerite", type="primary")
    if payroll_submitted:
        try:
            account_id = next(account["id"] for account in accounts if account["name"] == account_name)
            category_id = next(category["id"] for category in revenue_categories if category["name"] == category_name)
            create_manual_payroll(employer, competence, payment_date, money_to_cents(gross), money_to_cents(discounts), money_to_cents(net), account_id, category_id, notes, DEFAULT_DATABASE_PATH)
        except (ValueError, sqlite3.IntegrityError) as error:
            st.error(str(error))
        else:
            st.success("Holerite registrado. Apenas o salário líquido foi lançado como receita.")
            st.rerun()

if upload and accounts:
    data = upload.getvalue()
    suffix = Path(upload.name).suffix.casefold()
    if len(data) > MAX_FILE_SIZE:
        st.error("O arquivo excede o limite local de 10 MB.")
        st.stop()
    try:
        columns = []
        sheets = []
        if suffix == ".csv":
            delimiter = st.selectbox("Delimitador", ["Detecção automática", ";", ",", "\\t"])
            encoding = st.selectbox("Codificação", ["utf-8-sig", "latin-1"])
            columns, records = parse_csv(data, None if delimiter == "Detecção automática" else ("\t" if delimiter == "\\t" else delimiter), encoding)
        elif suffix == ".xlsx":
            import openpyxl
            workbook = openpyxl.load_workbook(data, read_only=True, data_only=True)
            sheets = workbook.sheetnames
            sheet = st.selectbox("Aba", sheets)
            sheets, columns, records = parse_excel(data, sheet)
        elif suffix == ".pdf":
            text, records = parse_pdf(data)
            st.info(f"PDF textual lido localmente. {len(text)} caracteres extraídos.")
        elif suffix == ".ofx":
            institution, records = parse_ofx(data)
            st.info(f"OFX lido localmente. Instituição detectada: {institution or 'não identificada'}.")
        else:
            st.error("Formato não suportado.")
            st.stop()
    except (ValueError, UnicodeDecodeError, pd.errors.ParserError) as error:
        st.error(f"Não foi possível interpretar o documento: {error}")
        st.stop()

    account_names = {account["name"]: account["id"] for account in accounts}
    account_name = st.selectbox("Conta de destino", list(account_names))
    categories = list_categories(database_path=DEFAULT_DATABASE_PATH)
    category_names = [category["name"] for category in categories]
    records = mark_duplicates(records, account_names[account_name], DEFAULT_DATABASE_PATH)
    table = pd.DataFrame([record.to_dict() for record in records])
    if table.empty:
        st.warning("Nenhuma operação estruturada foi encontrada. Revise o documento ou faça o lançamento manualmente.")
    else:
        table.insert(0, "Importar", table["status"].eq("Pronto") & ~table["is_duplicate"])
        table["amount"] = table["amount_cents"].apply(lambda value: cents_to_brl(value) if pd.notna(value) else "")
        edited = st.data_editor(table, width="stretch", hide_index=True, num_rows="dynamic", column_config={"Importar": st.column_config.CheckboxColumn(required=True), "category_name": st.column_config.SelectboxColumn(options=category_names), "amount_cents": None, "is_duplicate": st.column_config.CheckboxColumn(disabled=True)})
        st.caption("Revise campos obrigatórios, categorias e possíveis duplicidades antes de confirmar.")
        confirmed = st.checkbox("Confirmo a importação dos registros selecionados.")
        if st.button("Importar selecionados", type="primary", disabled=not confirmed):
            selected_records = []
            for row in edited.to_dict("records"):
                if not row.get("Importar"):
                    continue
                record = ImportRecord(transaction_date=str(row.get("transaction_date", "")), description=str(row.get("description", "")), amount_cents=row.get("amount_cents"), transaction_type=str(row.get("transaction_type", "")), external_id=str(row.get("external_id", "")), institution=str(row.get("institution", "")), category_name=str(row.get("category_name", "")), status="Pronto", is_duplicate=bool(row.get("is_duplicate")))
                selected_records.append(record)
            try:
                category_ids = {category["name"]: category["id"] for category in categories}
                imported = import_records(selected_records, account_names[account_name], category_ids, document_hash(data), DEFAULT_DATABASE_PATH)
            except (ValueError, sqlite3.IntegrityError) as error:
                st.error(str(error))
            else:
                st.success(f"{imported} lançamento(s) importado(s) com sucesso.")
                st.rerun()

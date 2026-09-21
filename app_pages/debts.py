from datetime import date
import sqlite3
import streamlit as st

from src.accounts import cents_to_brl, list_accounts, money_to_cents
from src.debts import create_debt, create_debt_payment, debt_totals, list_debt_payments, list_debts
from src.database import DEFAULT_DATABASE_PATH

st.header("Dívidas")
with st.form("debt_form", clear_on_submit=True):
    name = st.text_input("Descrição")
    creditor = st.text_input("Credor ou instituição")
    initial = st.text_input("Valor inicial")
    remaining = st.text_input("Saldo devedor inicial")
    reference = st.date_input("Data de referência", date.today())
    due = st.date_input("Vencimento (opcional)", value=None)
    installments = st.number_input("Número de parcelas (opcional)", min_value=1, value=1)
    installment = st.text_input("Valor previsto da parcela (opcional)")
    interest = st.text_input("Taxa de juros (informativa)")
    notes = st.text_area("Observações")
    submitted = st.form_submit_button("Cadastrar dívida", type="primary")
if submitted:
    try:
        create_debt(name, creditor, money_to_cents(initial), money_to_cents(remaining), reference, due, int(installments), money_to_cents(installment) if installment.strip() else None, interest, notes, DEFAULT_DATABASE_PATH)
    except (ValueError, sqlite3.IntegrityError) as error: st.error(str(error))
    else: st.success("Dívida cadastrada."); st.rerun()
rows = list_debts(DEFAULT_DATABASE_PATH)
st.metric("Total de dívidas", cents_to_brl(debt_totals(DEFAULT_DATABASE_PATH)["principal_cents"]))
for debt in rows:
    st.container(border=True).write(f"**{debt['name']}** | {debt['creditor']} | Saldo: {cents_to_brl(debt['principal_remaining_cents'])}")
    with st.expander(f"Pagamentos: {debt['name']}"):
        accounts = list_accounts(DEFAULT_DATABASE_PATH)
        if accounts and debt["principal_remaining_cents"] > 0:
            with st.form(f"debt_payment_{debt['id']}"):
                account = st.selectbox("Conta", [a["name"] for a in accounts])
                amount = st.text_input("Valor pago")
                principal = st.text_input("Amortização do principal")
                interest_paid = st.text_input("Juros e encargos", value="0,00")
                payment_date = st.date_input("Data", date.today())
                if st.form_submit_button("Registrar pagamento"):
                    try:
                        create_debt_payment(debt["id"], next(a["id"] for a in accounts if a["name"] == account), money_to_cents(amount), money_to_cents(principal), money_to_cents(interest_paid), payment_date, database_path=DEFAULT_DATABASE_PATH)
                    except (ValueError, sqlite3.IntegrityError) as error: st.error(str(error))
                    else: st.success("Pagamento registrado."); st.rerun()
        payments = list_debt_payments(debt["id"], DEFAULT_DATABASE_PATH)
        st.write([{"Data": p["payment_date"], "Valor": cents_to_brl(p["amount_cents"]), "Principal": cents_to_brl(p["principal_cents"]), "Juros": cents_to_brl(p["interest_cents"])} for p in payments])

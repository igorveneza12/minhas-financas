from datetime import date
import sqlite3

import pandas as pd
import streamlit as st

from src.accounts import cents_to_brl, list_accounts, money_to_cents
from src.credit_cards import (
    create_payment,
    delete_payment,
    invoice_installments,
    list_cards,
    list_invoices,
    list_payments,
)
from src.database import DEFAULT_DATABASE_PATH


st.header("Faturas")
cards = list_cards(DEFAULT_DATABASE_PATH, include_archived=True)
if not cards:
    st.info("Cadastre um cartão para consultar faturas.")
else:
    card_options = {card["name"]: card["id"] for card in cards}
    card_name = st.selectbox("Cartão", list(card_options))
    card_id = card_options[card_name]
    invoices = list_invoices(DEFAULT_DATABASE_PATH, card_id)
    if not invoices:
        st.info("Este cartão ainda não possui faturas com parcelas.")
    else:
        st.dataframe(
            pd.DataFrame([
                {
                    "Fatura": f"{invoice['billing_month']:02d}/{invoice['billing_year']}",
                    "Fechamento": invoice["closing_date"],
                    "Vencimento": invoice["due_date"],
                    "Total": cents_to_brl(invoice["total_cents"]),
                    "Pago": cents_to_brl(invoice["paid_cents"]),
                    "Pendente": cents_to_brl(invoice["pending_cents"]),
                    "Status": invoice["status"],
                }
                for invoice in invoices
            ]),
            hide_index=True,
            width="stretch",
        )
        invoice_options = {
            f"{invoice['billing_month']:02d}/{invoice['billing_year']} | {invoice['status']} | {cents_to_brl(invoice['pending_cents'])}": invoice
            for invoice in invoices
        }
        selected_label = st.selectbox("Fatura para consultar ou pagar", list(invoice_options))
        selected = invoice_options[selected_label]
        st.subheader("Parcelas da fatura")
        installments = invoice_installments(selected["id"], DEFAULT_DATABASE_PATH)
        st.dataframe(
            pd.DataFrame([
                {
                    "Compra": row["description"],
                    "Parcela": row["installment_number"],
                    "Valor": cents_to_brl(row["amount_cents"]),
                    "Categoria": row["category_name"],
                }
                for row in installments
            ]),
            hide_index=True,
            width="stretch",
        )

        if selected["pending_cents"] > 0:
            accounts = list_accounts(DEFAULT_DATABASE_PATH)
            if accounts:
                account_options = {account["name"]: account["id"] for account in accounts}
                with st.form("payment_form", clear_on_submit=True):
                    payment_amount = st.text_input("Valor pago", value=cents_to_brl(selected["pending_cents"]).replace("R$ ", ""))
                    account_name = st.selectbox("Conta utilizada", list(account_options))
                    payment_date = st.date_input("Data do pagamento", value=date.today())
                    notes = st.text_area("Observações (opcional)")
                    submitted = st.form_submit_button("Registrar pagamento", type="primary")
                if submitted:
                    try:
                        create_payment(
                            selected["id"], account_options[account_name], money_to_cents(payment_amount),
                            payment_date, notes, database_path=DEFAULT_DATABASE_PATH,
                        )
                    except (ValueError, sqlite3.IntegrityError) as error:
                        st.error(str(error))
                    else:
                        st.success("Pagamento registrado; o saldo da conta foi atualizado.")
                        st.rerun()
            else:
                st.warning("Cadastre uma conta ativa para pagar a fatura.")

        payments = list_payments(selected["id"], DEFAULT_DATABASE_PATH)
        if payments:
            st.subheader("Pagamentos registrados")
            st.dataframe(
                pd.DataFrame([
                    {
                        "Data": payment["payment_date"],
                        "Conta": payment["account_name"],
                        "Valor": cents_to_brl(payment["amount_cents"]),
                        "Observações": payment["notes"] or "",
                    }
                    for payment in payments
                ]),
                hide_index=True,
                width="stretch",
            )
            payment_options = {
                f"#{payment['id']} | {payment['payment_date']} | {cents_to_brl(payment['amount_cents'])}": payment
                for payment in payments
            }
            payment_label = st.selectbox("Pagamento para reverter", list(payment_options))
            payment = payment_options[payment_label]
            confirmed = st.checkbox("Confirmo a reversão deste pagamento.", key=f"confirm_payment_{payment['id']}")
            if st.button("Reverter pagamento", disabled=not confirmed, key=f"reverse_payment_{payment['id']}"):
                try:
                    delete_payment(payment["id"], DEFAULT_DATABASE_PATH)
                except ValueError as error:
                    st.error(str(error))
                else:
                    st.success("Pagamento revertido; o saldo da conta foi restaurado.")
                    st.rerun()

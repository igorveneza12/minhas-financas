"""Cadastro de transferências internas, sem impacto nas receitas/despesas."""
from datetime import date
import sqlite3

import pandas as pd
import streamlit as st

from src.accounts import cents_to_brl, list_accounts, money_to_cents
from src.database import DEFAULT_DATABASE_PATH
from src.transfers import create_transfer, delete_transfer, list_transfers


st.header("Transferências entre contas")
st.caption(
    "Movimente dinheiro entre suas próprias contas sem gerar receita ou despesa. "
    "Não registre novamente os dois lados do Pix em Movimentações."
)

accounts = list_accounts(DEFAULT_DATABASE_PATH)
if len(accounts) < 2:
    st.info("Cadastre pelo menos duas contas ativas antes de registrar uma transferência.")
else:
    choices = {f"{row['name']} — #{row['id']}": row["id"] for row in accounts}
    with st.form("new_transfer", clear_on_submit=True):
        source_label = st.selectbox("Conta de origem", list(choices))
        destination_label = st.selectbox("Conta de destino", list(choices), index=1)
        amount = st.text_input("Valor (R$)", placeholder="Ex.: 1.163,43")
        day = st.date_input("Data da transferência", value=date.today(), format="DD/MM/YYYY")
        notes = st.text_input("Observações (opcional)")
        submitted = st.form_submit_button("Registrar transferência", type="primary")
    if submitted:
        try:
            create_transfer(
                choices[source_label], choices[destination_label],
                money_to_cents(amount), day, notes, DEFAULT_DATABASE_PATH,
            )
        except (ValueError, sqlite3.IntegrityError) as error:
            st.error(str(error))
        else:
            st.success("Transferência registrada sem alterar receitas ou despesas.")
            st.rerun()

records = list_transfers(DEFAULT_DATABASE_PATH)
if records:
    st.subheader("Transferências registradas")
    st.dataframe(
        pd.DataFrame([
            {
                "ID": row["id"],
                "Data": row["transfer_date"],
                "Origem": row["source_name"],
                "Destino": row["destination_name"],
                "Valor": cents_to_brl(row["amount_cents"]),
                "Observações": row["notes"] or "",
            }
            for row in records
        ]),
        hide_index=True,
        width="stretch",
    )
    options = {
        f"#{row['id']} — {row['transfer_date']} — {row['source_name']} → {row['destination_name']} — {cents_to_brl(row['amount_cents'])}": row["id"]
        for row in records
    }
    with st.expander("Excluir uma transferência lançada incorretamente"):
        chosen = st.selectbox("Transferência", list(options))
        confirmed = st.checkbox("Confirmo a exclusão deste registro de transferência.")
        if st.button("Excluir transferência", disabled=not confirmed):
            try:
                delete_transfer(options[chosen], DEFAULT_DATABASE_PATH)
            except ValueError as error:
                st.error(str(error))
            else:
                st.success("Transferência excluída.")
                st.rerun()

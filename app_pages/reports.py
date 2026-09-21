"""Relatórios financeiros simples do período selecionado."""
from calendar import monthrange
from datetime import date

import pandas as pd
import streamlit as st

from src.accounts import cents_to_brl, list_accounts
from src.categories import list_categories
from src.database import DEFAULT_DATABASE_PATH
from src.reports import period_report, report_csv, report_excel

st.header("Relatórios")
st.caption("Despesas diretas por data e parcelas de cartão pelo vencimento; pagamentos de fatura não geram nova despesa.")

period = st.session_state.pop("report_from_dashboard", None)
if period:
    year, month = period
    st.session_state["reports_start"] = date(year, month, 1)
    st.session_state["reports_end"] = date(year, month, monthrange(year, month)[1])
elif "reports_start" not in st.session_state or "reports_end" not in st.session_state:
    today = date.today()
    st.session_state["reports_start"] = date(today.year, today.month, 1)
    st.session_state["reports_end"] = date(today.year, today.month, monthrange(today.year, today.month)[1])

col_start, col_end = st.columns(2)
with col_start:
    start = st.date_input("Data inicial", key="reports_start", format="DD/MM/YYYY")
with col_end:
    end = st.date_input("Data final", key="reports_end", format="DD/MM/YYYY")

accounts = list_accounts(DEFAULT_DATABASE_PATH, include_archived=True)
account_choices = {f"{row['name']}{' (arquivada)' if not row['active'] else ''} — #{row['id']}": row["id"] for row in accounts}
category_rows = list_categories(database_path=DEFAULT_DATABASE_PATH)
category_choices = {f"{row['name']} ({row['category_type']}) — #{row['id']}": row["id"] for row in category_rows}
col_acc, col_cat = st.columns(2)
with col_acc:
    chosen_account = st.selectbox("Conta", ["Todas"] + list(account_choices))
with col_cat:
    chosen_category = st.selectbox("Categoria", ["Todas"] + list(category_choices))
if chosen_account != "Todas":
    st.caption("O filtro por conta exibe apenas receitas e despesas diretas; compras no cartão aparecem em 'Todas'.")

try:
    report = period_report(start, end, DEFAULT_DATABASE_PATH,
                           account_choices.get(chosen_account), category_choices.get(chosen_category))
except ValueError as error:
    st.error(str(error))
    st.stop()

c1, c2, c3 = st.columns(3)
c1.metric("Receitas", cents_to_brl(report["revenue_cents"]))
c2.metric("Despesas", cents_to_brl(report["expense_cents"]))
c3.metric("Resultado", cents_to_brl(report["result_cents"]))

st.subheader("Despesas por categoria")
if report["categories"]:
    st.dataframe(pd.DataFrame([{"Categoria": name, "Total": cents_to_brl(value)}
                              for name, value in sorted(report["categories"].items())]),
                 hide_index=True, width="stretch")
else:
    st.info("Nenhuma despesa para os filtros selecionados.")

st.subheader("Saldos atuais por conta")
st.caption("Posição atual de cada conta; estes saldos não representam o fechamento histórico do período filtrado.")
if accounts:
    st.dataframe(pd.DataFrame([{
        "Conta": a["name"],
        "Status": "Ativa" if a["active"] else "Arquivada",
        "Saldo atual": cents_to_brl(a["balance_cents"]),
    } for a in accounts]), hide_index=True, width="stretch")
else:
    st.info("Nenhuma conta cadastrada.")

st.subheader("Lançamentos do período")
entries = report["entries"]
if entries:
    st.dataframe(pd.DataFrame([{
        "Data": entry["date"], "Tipo": entry["type"], "Descrição": entry["description"],
        "Categoria": entry["category"], "Conta ou cartão": entry["account"],
        "Origem": entry["origin"], "Valor": cents_to_brl(entry["amount_cents"])
    } for entry in entries]), hide_index=True, width="stretch")
else:
    st.info("Nenhum lançamento encontrado.")

file_name = f"relatorio-{start.isoformat()}-a-{end.isoformat()}"
col_csv, col_excel = st.columns(2)
with col_csv:
    st.download_button("Baixar CSV", report_csv(entries), file_name=file_name + ".csv",
                       mime="text/csv", use_container_width=True)
with col_excel:
    st.download_button("Baixar Excel", report_excel(entries), file_name=file_name + ".xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)

from datetime import date
import sqlite3
import streamlit as st

from src.accounts import cents_to_brl, money_to_cents
from src.budget import budget_summary, copy_budgets, delete_budget, list_budget_status, upsert_budget
from src.categories import list_categories
from src.database import DEFAULT_DATABASE_PATH

st.header("Orçamento")
year = st.number_input("Ano", 2000, 2100, date.today().year, key="budget_year")
month = st.selectbox("Mês", range(1, 13), index=date.today().month - 1, format_func=lambda value: f"{value:02d}", key="budget_month")
categories = list_categories("despesa", DEFAULT_DATABASE_PATH)
options = {row["name"]: row["id"] for row in categories}
with st.form("budget_form", clear_on_submit=True):
    category_name = st.selectbox("Categoria", list(options))
    limit = st.text_input("Limite", placeholder="0,00")
    submitted = st.form_submit_button("Salvar limite", type="primary")
if submitted:
    try:
        upsert_budget(options[category_name], int(year), int(month), money_to_cents(limit), DEFAULT_DATABASE_PATH)
    except (ValueError, sqlite3.IntegrityError) as error: st.error(str(error))
    else: st.success("Limite orçamentário salvo."); st.rerun()
if st.button("Copiar limites do mês anterior"):
    previous_year, previous_month = (int(year), int(month) - 1) if int(month) > 1 else (int(year) - 1, 12)
    copied = copy_budgets(previous_year, previous_month, int(year), int(month), DEFAULT_DATABASE_PATH)
    st.success(f"{copied} limite(s) copiado(s)."); st.rerun()
summary = budget_summary(int(year), int(month), DEFAULT_DATABASE_PATH)
st.metric("Orçamento total", cents_to_brl(summary["limit_cents"])); st.metric("Gasto", cents_to_brl(summary["spent_cents"])); st.metric("Disponível", cents_to_brl(summary["limit_cents"] - summary["spent_cents"]))
rows = list_budget_status(int(year), int(month), DEFAULT_DATABASE_PATH)
for row in rows:
    used = row["spent_cents"] / row["limit_cents"] if row["limit_cents"] else 0
    color = "🔴" if used >= 1 else "🟡" if used >= .8 else "🟢"
    st.write(f"{color} **{row['category_name']}**: {cents_to_brl(row['spent_cents'])} / {cents_to_brl(row['limit_cents'])} ({used:.2%})")
    if st.button("Excluir limite", key=f"delete_budget_{row['id']}"):
        delete_budget(row["id"], DEFAULT_DATABASE_PATH); st.rerun()

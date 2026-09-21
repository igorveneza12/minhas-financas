from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st

from src.accounts import cents_to_brl, list_accounts
from src.database import DEFAULT_DATABASE_PATH
from src.data_management import create_backup
from src.dashboard import recent_transactions
from src.credit_cards import (
    card_future_commitments,
    list_cards,
    monthly_card_expenses_by_category,
    monthly_card_totals,
    unpaid_invoices_total,
    upcoming_invoices_total,
)
from src.budget import budget_summary
from src.debts import debt_totals
from src.goals import goals_summary
from src.recurring import recurring_summary
from src.transactions import monthly_comparison, monthly_expenses_by_category, monthly_totals, total_balance_cents


st.header("Dashboard")
today = date.today()
col_year, col_month = st.columns(2)
with col_year:
    year = st.number_input("Ano", min_value=2000, max_value=2100, value=today.year, step=1)
with col_month:
    month = st.selectbox("Mês", list(range(1, 13)), index=today.month - 1, format_func=lambda value: f"{value:02d}")

action_report, action_backup = st.columns(2)
with action_report:
    if st.button("Gerar relatório", use_container_width=True):
        st.session_state["report_from_dashboard"] = (int(year), int(month))
        st.switch_page("app_pages/reports.py")
with action_backup:
    if st.button("Preparar backup", use_container_width=True):
        try:
            backup_path = create_backup(DEFAULT_DATABASE_PATH)
            st.session_state["dashboard_backup"] = (backup_path.name, backup_path.read_bytes())
        except (OSError, ValueError) as error:
            st.error(f"Não foi possível gerar o backup: {error}")
if "dashboard_backup" in st.session_state:
    backup_name, backup_content = st.session_state["dashboard_backup"]
    st.download_button("Baixar backup", backup_content, file_name=backup_name,
                       mime="application/x-sqlite3")

summary = monthly_totals(int(year), int(month), DEFAULT_DATABASE_PATH)
revenue = summary["receita"]
direct_expenses = summary["despesa"]
card_expenses = monthly_card_totals(int(year), int(month), DEFAULT_DATABASE_PATH)["despesa_cartao"]
expenses = direct_expenses + card_expenses
result = revenue - expenses
budget = budget_summary(int(year), int(month), DEFAULT_DATABASE_PATH)
debts = debt_totals(DEFAULT_DATABASE_PATH)
goals = goals_summary(DEFAULT_DATABASE_PATH)
recurring = recurring_summary(int(year), int(month), DEFAULT_DATABASE_PATH)

def metric_group(title: str, metrics: list[tuple[str, str]]) -> None:
    st.subheader(title)
    with st.container(horizontal=True):
        for label, value in metrics:
            st.metric(label, value, border=True)


metric_group("Visão geral", [
    ("Receitas do mês", cents_to_brl(revenue)),
    ("Despesas diretas", cents_to_brl(direct_expenses)),
    ("Despesas do cartão", cents_to_brl(card_expenses)),
    ("Despesas totais", cents_to_brl(expenses)),
    ("Resultado mensal", cents_to_brl(result)),
    ("Orçamento do mês", cents_to_brl(budget["limit_cents"])),
    ("Disponível no orçamento", cents_to_brl(budget["limit_cents"] - budget["spent_cents"])),
])

metric_group("Contas", [
    ("Saldo consolidado", cents_to_brl(total_balance_cents(DEFAULT_DATABASE_PATH))),
])

st.subheader("Saldos por conta")
accounts = list_accounts(DEFAULT_DATABASE_PATH, include_archived=True)
if accounts:
    with st.container(horizontal=True):
        for account in accounts:
            st.metric(account["name"] + (" (arquivada)" if not account["active"] else ""), cents_to_brl(account["balance_cents"]), border=True)
else:
    st.info("Nenhuma conta ativa cadastrada.")

metric_group("Cartões", [
    ("Faturas em aberto", cents_to_brl(unpaid_invoices_total(DEFAULT_DATABASE_PATH))),
    ("Limite disponível", cents_to_brl(sum(card["available_cents"] for card in list_cards(DEFAULT_DATABASE_PATH)))),
])

metric_group("Dívidas", [
    ("Dívidas (principal)", cents_to_brl(debts["principal_cents"])),
])

metric_group("Metas", [
    ("Metas reservadas", cents_to_brl(goals["reserved_cents"])),
])

metric_group("Recorrências", [
    ("Previstas", cents_to_brl(recurring["previstas_cents"])),
    ("Pagas", cents_to_brl(recurring["pagas_cents"])),
    ("Pendentes", cents_to_brl(recurring["pendentes_cents"])),
])

expenses_rows = monthly_expenses_by_category(int(year), int(month), DEFAULT_DATABASE_PATH)
card_expenses_rows = monthly_card_expenses_by_category(int(year), int(month), DEFAULT_DATABASE_PATH)
comparison_rows = monthly_comparison(int(year), DEFAULT_DATABASE_PATH)
comparison_data = []
for row in comparison_rows:
    card_month = monthly_card_totals(int(year), int(row["month"].split("-")[1]), DEFAULT_DATABASE_PATH)["despesa_cartao"]
    comparison_data.append({
        "Mês": row["month"],
        "Receitas": row["receitas_cents"] / 100,
        "Despesas": (row["despesas_cents"] + card_month) / 100,
    })
chart_col, trend_col = st.columns(2)
with chart_col:
    st.subheader("Despesas por categoria")
    combined_categories = {}
    for row in expenses_rows:
        combined_categories[row["category_name"]] = combined_categories.get(row["category_name"], 0) + row["total_cents"]
    for row in card_expenses_rows:
        combined_categories[row["category_name"]] = combined_categories.get(row["category_name"], 0) + row["total_cents"]
    if combined_categories:
        expense_df = pd.DataFrame([{"Categoria": name, "Valor": cents / 100} for name, cents in combined_categories.items()])
        st.plotly_chart(px.bar(expense_df, x="Categoria", y="Valor", labels={"Valor": "R$"}), width="stretch")
    else:
        st.info("Não há despesas neste mês.")
with trend_col:
    st.subheader(f"Receitas e despesas em {int(year)}")
    comparison_df = pd.DataFrame(comparison_data)
    st.plotly_chart(px.line(comparison_df, x="Mês", y=["Receitas", "Despesas"], markers=True, labels={"value": "R$"}), width="stretch")

future_rows = card_future_commitments(DEFAULT_DATABASE_PATH)
st.subheader("Próximas faturas e compromissos futuros")
st.metric("Próximas faturas", cents_to_brl(upcoming_invoices_total(DEFAULT_DATABASE_PATH)))
if future_rows:
    future_df = pd.DataFrame([
        {"Vencimento": row["due_date"], "Cartão": row["card_name"], "Valor": row["total_cents"] / 100}
        for row in future_rows
    ])
    st.plotly_chart(px.bar(future_df, x="Vencimento", y="Valor", color="Cartão", labels={"Valor": "R$"}), width="stretch")
else:
    st.info("Nenhuma parcela futura cadastrada.")

st.subheader("Movimentações recentes")
recent = recent_transactions(database_path=DEFAULT_DATABASE_PATH)
if recent:
    st.dataframe(
        pd.DataFrame([
            {
                "Data": row["transaction_date"],
                "Tipo": "Receita" if row["transaction_type"] == "receita" else "Despesa",
                "Descrição": row["description"],
                "Categoria": row["category_name"],
                "Valor": cents_to_brl(row["amount_cents"]),
            }
            for row in recent
        ]),
        hide_index=True,
        width="stretch",
    )
else:
    st.info("Nenhuma movimentação cadastrada.")

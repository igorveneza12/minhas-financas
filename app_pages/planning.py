import pandas as pd
import streamlit as st

from src.accounts import cents_to_brl
from src.database import DEFAULT_DATABASE_PATH
from src.planning import monthly_planning

st.header("Planejamento")
year = st.number_input("Ano", 2000, 2100, 2026)
rows = monthly_planning(int(year), DEFAULT_DATABASE_PATH)
st.caption("Valores são previsões e não garantem resultados financeiros.")
st.dataframe(pd.DataFrame([{"Mês": r["month"], "Orçamentos": cents_to_brl(r["budget_cents"]), "Parcelas de cartão": cents_to_brl(r["card_cents"]), "Pagamentos de dívidas previstos": cents_to_brl(r["debt_cents"]), "Valores planejados para metas": cents_to_brl(r["goals_cents"])} for r in rows]), hide_index=True, width="stretch")

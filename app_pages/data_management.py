import streamlit as st

from src.data_management import (
    backup_bytes,
    create_backup,
    reset_database,
    restore_database,
    validate_backup_bytes,
)
from src.database import DEFAULT_DATABASE_PATH, initialize_database


st.header("Gerenciamento de dados")
st.caption("Faça backups antes de operações destrutivas. Os arquivos de backup permanecem na pasta backups/.")

initialize_database(DEFAULT_DATABASE_PATH)

st.subheader("Reset geral")
st.warning("Esta operação apaga os registros financeiros do banco atual e preserva apenas a estrutura e as categorias padrão.")
if st.button("Apagar todos os dados", type="secondary"):
    st.session_state["reset_backup_data"] = backup_bytes(DEFAULT_DATABASE_PATH)
    st.session_state["reset_backup_ready"] = True
    st.session_state["reset_download_confirmed"] = False

if st.session_state.get("reset_backup_ready"):
    st.download_button(
        "Baixar backup antes do reset",
        data=st.session_state["reset_backup_data"],
        file_name="financeiro-antes-do-reset.db",
        mime="application/x-sqlite3",
        on_click=lambda: st.session_state.update(reset_download_confirmed=True),
    )
    downloaded = st.checkbox("Confirmo que baixei o backup.", key="reset_download_confirmed")
    confirmation = st.text_input("Digite EXCLUIR TUDO para confirmar", type="password")
    if st.button("Confirmar reset", disabled=not (downloaded and confirmation == "EXCLUIR TUDO")):
        backup_path = reset_database(DEFAULT_DATABASE_PATH)
        st.session_state.pop("reset_backup_ready", None)
        st.session_state.pop("reset_backup_data", None)
        st.success(f"Reset concluído. Backup preservado em {backup_path.name}.")
        st.rerun()

st.divider()
st.subheader("Restaurar backup")
backup_file = st.file_uploader("Selecione um backup SQLite", type=["db", "sqlite", "sqlite3"])
if backup_file:
    backup_data = backup_file.getvalue()
    valid, message = validate_backup_bytes(backup_data)
    if valid:
        st.success(message)
        confirmed = st.checkbox("Confirmo substituir os dados atuais pelo backup selecionado.")
        if st.button("Restaurar backup", disabled=not confirmed):
            try:
                current_backup = restore_database(backup_data, DEFAULT_DATABASE_PATH)
            except ValueError as error:
                st.error(str(error))
            else:
                st.success(f"Backup restaurado. Cópia do banco anterior preservada em {current_backup.name}.")
                st.rerun()
    else:
        st.error(message)

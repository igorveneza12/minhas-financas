# Minhas Finanças

Aplicação local para controle financeiro doméstico. A versão 0.6 adiciona despesas recorrentes mensais à central local de importação da versão 0.5.

## Requisitos

- Python 3.11 ou superior (testado com Python 3.13.7)
- Windows PowerShell

## Configuração

Na pasta do projeto, execute:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

O ambiente virtual pode ser usado diretamente, sem ativação do PowerShell.

## Execução

```powershell
.\.venv\Scripts\streamlit.exe run app.py
```

O banco será criado automaticamente em `data/financeiro.db`. A inicialização cria apenas tabelas ausentes e não apaga dados existentes.

Ao atualizar um banco existente, faça primeiro um backup consistente com a API de backup do SQLite. A implementação desta versão usa essa política antes de alterações no banco.

## Testes

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Os testes usam bancos temporários e não acessam o banco real da aplicação.

## Estrutura

- `app.py`: entrada e navegação da aplicação.
- `app_pages/`: telas de Dashboard, Contas, Movimentações e Categorias.
- `src/database.py`: conexão, esquema e inicialização SQLite.
- `src/accounts.py`: regras de contas, saldos e conversão monetária.
- `src/categories.py`: categorias padrão e personalizadas.
- `src/transactions.py`: CRUD, filtros e cálculos de movimentações.
- `src/credit_cards.py`: cartões, compras, parcelas, faturas e pagamentos.
- `src/dashboard.py`: consultas das movimentações recentes.
- `app_pages/cards.py`: cadastro e manutenção de cartões.
- `app_pages/purchases.py`: compras à vista e parceladas.
- `app_pages/invoices.py`: faturas, pagamentos e reversões.
- `app_pages/budget.py`: limites mensais por categoria e execução do orçamento.
- `app_pages/debts.py`: dívidas externas aos cartões e pagamentos com principal/juros.
- `app_pages/goals.py`: metas com progresso informado manualmente.
- `app_pages/planning.py`: compromissos previstos por mês.
- `src/importers.py`: parsing local, classificação heurística, deduplicação e gravação confirmada.
- `app_pages/imports.py`: envio, pré-visualização editável e confirmação de documentos.
- `src/recurring.py`: previsões mensais, pagamentos e vínculos com despesas existentes.
- `app_pages/recurring.py`: cadastro e acompanhamento de despesas recorrentes.
- `src/data_management.py`: backup, validação, reset e restauração do banco SQLite.
- `app_pages/data_management.py`: gerenciamento de dados em Configurações.
- `tests/`: testes automatizados.
- `data/financeiro.db`: banco local gerado em tempo de execução.

## Como usar

1. Em **Contas**, cadastre uma conta com nome, tipo e saldo inicial.
2. Em **Movimentações**, escolha **Receita** ou **Despesa**, informe descrição, valor, data, conta e categoria, e envie o formulário.
3. Em **Dashboard**, selecione mês e ano para consultar receitas, despesas, resultado e gráficos.
4. Em **Categorias**, cadastre categorias personalizadas quando as categorias padrão não forem suficientes.
5. Em **Orçamento**, defina limites por categoria e mês; despesas diretas e parcelas de cartão entram na competência escolhida.
6. Em **Dívidas**, cadastre apenas obrigações que não sejam faturas de cartão e registre pagamentos separando principal e juros.
7. Em **Metas financeiras**, acompanhe valores reservados manualmente sem alterar o saldo das contas.
8. Em **Planejamento**, consulte orçamentos, parcelas, pagamentos previstos e valores planejados para metas, separados por natureza.
9. Em **Importar documentos**, envie um CSV, Excel, PDF textual ou OFX, revise a tabela e confirme somente os registros desejados.
10. Em **Recorrentes**, cadastre despesas mensais, revise previsões e confirme pagamentos. Previsões não alteram o saldo até o pagamento.
11. Em **Configurações > Gerenciamento de dados**, baixe um backup antes do reset ou restaure um backup SQLite válido após confirmação explícita.

### Importação de documentos

- **CSV**: detecção ou seleção de delimitador e codificação; colunas de data, descrição e valor são detectadas quando os nomes são conhecidos.
- **Excel**: abas são identificadas e o usuário escolhe a aba antes da pré-visualização.
- **PDF textual**: extrai padrões simples de data, descrição e valor; layouts complexos exigem revisão manual.
- **OFX**: extrai data, descrição, valor e FITID com parser local.
- **Holerite**: não há reconhecimento automático; use o formulário manual para informar bruto, descontos e líquido. Apenas o líquido vira receita, e o demonstrativo fica separado.
- O arquivo é limitado a 10 MB, não é armazenado permanentemente e não é enviado para APIs externas.
- A gravação só ocorre após confirmação explícita. O hash do arquivo e o histórico do lote impedem reimportação acidental.
- O sistema não cria contas, cartões ou categorias automaticamente; a conta de destino deve ser ativa e a categoria precisa ser revisada.

### Cartões e faturas

1. Em **Cartões de crédito**, cadastre o limite, o dia de fechamento e o vencimento.
2. Em **Compras no cartão**, informe o cartão, o valor total e o número de parcelas. A divisão é feita em centavos e a soma das parcelas é exatamente igual ao total.
3. Em **Faturas**, selecione o cartão e a fatura para consultar parcelas ou registrar pagamento total/parcial usando uma conta ativa.
4. O pagamento reduz o saldo da conta bancária e a obrigação da fatura, mas não cria uma nova despesa no orçamento.

### Regra do ciclo

Compras realizadas até o dia de fechamento, inclusive no próprio dia, entram na fatura do mês seguinte. Compras depois do fechamento entram na fatura do mês posterior. Assim, com fechamento no dia 20 e vencimento no dia 10, uma compra em 19/09 ou 20/09 vence em 10/10; uma compra em 21/09 vence em 10/11. Dias inexistentes são ajustados para o último dia válido do mês.

### Excluir, arquivar e reativar contas

- Uma conta sem movimentações pode ser excluída permanentemente após confirmação explícita.
- Uma conta com movimentações não pode ser apagada. Use **Arquivar conta** para preservar o histórico.
- Contas arquivadas deixam de aparecer em novos lançamentos, mas continuam no saldo consolidado e nos relatórios históricos.
- A seção **Contas arquivadas** permite reativar uma conta para novos lançamentos.

## Limitações da versão 0.6

Esta versão não possui OCR, inteligência artificial, parser automático de holerites, reconhecimento completo de faturas de cartão, vinculação automática de comprovantes, importação automática para compras/faturas/dívidas ou integração bancária. PDFs precisam conter texto selecionável e podem exigir revisão manual. A classificação é heurística e nunca deve ser tratada como identificação garantida. Recorrências são mensais; pagamentos de cartão não são gerados pelo módulo de recorrentes.

## Relatórios e gestão de dados

- Em **Relatórios**, selecione o período e, opcionalmente, a conta e a categoria. Baixe a listagem em CSV ou Excel. As parcelas do cartão entram pelo vencimento da fatura; o pagamento não é contabilizado como nova despesa. Ao filtrar uma conta bancária, o relatório exibe apenas as movimentações diretas dessa conta.
- No **Dashboard**, **Gerar relatório** abre a página com o mês selecionado e **Preparar backup** cria uma cópia consistente do SQLite e disponibiliza o download.
- Em **Metas financeiras**, metas sem valor reservado podem ser excluídas mediante confirmação. Metas com reserva manual podem ser arquivadas e depois reativadas. Essas ações não alteram saldos bancários.
- Em **Configurações > Gerenciamento de dados**, o reset e a restauração já estão disponíveis. Para testar, use **somente uma cópia fictícia do banco**. O reset exige download/confirmação de backup e a frase `EXCLUIR TUDO`. A restauração exige validação e confirmação.

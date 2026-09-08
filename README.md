# 🛒 Shopping List Intelligence

Sistema inteligente de lista de compras com arquitetura **Medallion** (Raw → Bronze → Silver), extração de dados via OCR com **Gemini AI** e dashboard analítico em **Streamlit**.

## Arquitetura

```
📷 Nota Fiscal / 📄 CSV
        │
        ▼
┌─────────────────┐
│   🗄️ RAW        │  Dados brutos (append-only)
│  raw_purchases   │  Strings, sem transformação
└────────┬────────┘
         │  ETL: limpeza + tipagem + reconciliação qtd/unitário/total
         ▼
┌─────────────────┐
│   🗄️ BRONZE     │  Dados limpos e normalizados
│ bronze_purchases │  Tipos corretos, nomes padronizados,
│                  │  quantity + unit_price (product_price = total da linha),
│                  │  access_key + nfce_url (dados do QR da NFC-e)
└────────┬────────┘
         │  ETL: agregações
         ▼
┌─────────────────────────────────────────┐
│   🗄️ SILVER                             │
│  silver_product_stats   → por produto   │
│  silver_market_stats    → por mercado   │
│  silver_monthly_spending → por mês      │
└─────────────────────────────────────────┘
         │
         ▼
    📊 Streamlit Dashboard
```

## Dashboard

| Aba | Descrição |
|-----|-----------|
| 🛒 Lista de Compras | Lista inteligente com flag "Precisa Comprar?" baseada na frequência de compra |
| 📈 Análise de Preços | Evolução de preço por produto, tabela com min/max/média |
| 🏪 Mercados | Gasto total, ticket médio e frequência por mercado |
| 📅 Tendências | Gastos mensais, itens por mês, preço médio e curva de recorrência de compra (total e por mercado) |
| 📥 Importar Dados | Upload de nota fiscal (OCR via Gemini) ou CSV, com quantidade, custo unitário e total por item |

## Tech Stack

- **Python 3.13** + **uv** (package manager)
- **Streamlit** — dashboard interativo
- **SQLAlchemy** + **PyMySQL** — ORM e conexão MySQL
- **Pandas** — transformações de dados
- **Google Gemini AI** — OCR de notas fiscais

## Estrutura do Projeto

```
shopping-list/
├── main.py                  # Dashboard Streamlit (entry point)
├── src/
│   ├── models.py            # Modelos SQLAlchemy (Raw, Bronze, Silver)
│   ├── database.py          # Gerenciador de conexões (3 databases)
│   ├── etl.py               # Pipeline ETL (raw→bronze→silver)
│   ├── gemini.py            # Integração com Gemini AI (OCR)
│   └── query/
│       ├── product_stats.sql
│       ├── market_stats.sql
│       └── monthly_spending.sql
├── template/
│   ├── prompt.md            # Prompt para o Gemini
│   └── response.json        # Schema de resposta esperado
├── Dockerfile
├── docker-compose.yml
└── pyproject.toml
```

## Setup

### 1. Variáveis de ambiente

Crie um arquivo `.env` na raiz do projeto:

```env
MYSQL_HOST=
MYSQL_PORT=3306
MYSQL_ID_TABLE=shopping_list
MYSQL_USER=
MYSQL_PASSWORD=

GEMINI_API_KEY=
```

### 2. Executar localmente

```bash
uv sync
uv run streamlit run main.py
```

### 3. Executar com Docker

```bash
docker compose up --build
```

O app estará disponível em `http://localhost:8502`.

> **Nota:** Na primeira execução, o app cria automaticamente os databases (`raw`, `bronze`, `silver`), tabelas, e migra dados existentes da tabela legada `shopping_list`.
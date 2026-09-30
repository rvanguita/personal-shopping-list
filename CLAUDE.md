# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Shopping List Intelligence — ingests grocery receipts (via Gemini OCR or CSV upload), runs them through a Medallion-style ETL pipeline (Raw → Bronze → Silver) in MySQL, and displays analytics (price trends, market comparison, monthly spending, a "what to buy" list). Two UIs share one backend:
- **Streamlit** (`app/streamlit`, Portuguese UI): import, edit, and analytics.
- **Dash** (`app/dash`, English UI, dark theme): read-only analytics dashboard.

### Layout (uv workspace)

- `src/shopping_list/` — shared backend package `shopping-list` (root `pyproject.toml`). **It must not import any UI framework.**
- `app/streamlit/` — member `shopping-list-streamlit`: `main.py` (thin entrypoint), `src/shopping_list_streamlit/app.py`, `.streamlit/config.toml`, `Dockerfile`.
- `app/dash/` — member `shopping-list-dash`: `main.py`, `src/shopping_list_dash/` (`views.py` view models, `figures.py` Plotly, `layout.py`, `callbacks.py`, `theme.py`, `formatting.py`, `data.py`, `assets/style.css`), `Dockerfile`.
- `docs/template/` — OCR prompt/response templates.
- Apps never import each other. A dependency goes in the pyproject of the package that imports it.
- Project paths are anchored in `src/shopping_list/config.py` (`PROJECT_ROOT`, `QUERY_DIR`, `PROMPT_PATH`, `RESPONSE_PATH`), never the cwd — each app runs from its own folder. `config.py` also loads the root `.env`.

## Commands

```bash
uv sync --all-packages --all-groups                      # install every workspace member
uv run --directory app/streamlit streamlit run main.py   # Streamlit (http://localhost:8501)
uv run --directory app/dash python main.py               # Dash (http://localhost:8050)
docker compose up --build        # both apps: Streamlit on :8502, Dash on :8503
uv run ruff check .              # lint
uv run ruff format .             # format
```

There is no test suite in this repo currently.

### Environment

Requires a `.env` file (gitignored) at the project root:

```env
MYSQL_HOST=
MYSQL_PORT=3306
MYSQL_ID_TABLE=shopping_list
MYSQL_USER=
MYSQL_PASSWORD=
GEMINI_API_KEY=
```

On first run, `DatabaseManager` auto-creates the three MySQL databases (`raw`, `bronze`, `silver`) and their tables, and migrates any existing data from the legacy `shopping_list` table. `DatabaseManager.migrate_schema()` (called right after `create_all_tables()`) applies additive `ADD COLUMN` migrations to pre-existing tables — `create_all_tables()` only creates missing tables, never alters them. New columns go in `SCHEMA_ADDITIONS` in `src/shopping_list/database.py`.

## Architecture

### Medallion pipeline across three separate MySQL databases

Unlike a typical single-schema medallion setup, each layer here is a **separate MySQL database** (not just a table/schema) on the same host — `raw`, `bronze`, `silver`. `src/shopping_list/database.py` (`DatabaseManager`) owns one SQLAlchemy engine per database and is the only place connections are created; Streamlit instantiates it once via `@st.cache_resource` (`get_db_manager`), Dash once per process (`shopping_list_dash/data.py`).

- **Raw** (`raw_purchases`, `src/shopping_list/models.py`): append-only, untyped strings straight from ingestion (OCR or CSV), plus `ingested_at`/`source_type`. Also carries per-receipt NFC-e metadata: `access_key` (44-digit chave de acesso) and `nfce_url` (the QR-code consultation URL), both nullable.
- **Bronze** (`bronze_purchases`): cleaned/typed rows (dates parsed, prices coerced to numeric, product/market names title-cased and stripped). `ETLPipeline.raw_to_bronze()` (`src/shopping_list/etl.py`) is incremental — it diffs `raw_purchases.id` against `bronze_purchases.raw_id` to find unprocessed rows. It also reconciles `quantity` (default 1) / `unit_price` / `product_price`: **`product_price` is the line total** (`quantity × unit_price`); a missing `unit_price` is derived as `product_price / quantity` and vice-versa, so the Silver SQL keeps summing `product_price` unchanged. `access_key` / `nfce_url` are carried through with only a strip (empty → NULL).
- **Silver** (`silver_product_stats`, `silver_market_stats`, `silver_monthly_spending`): aggregates for the dashboard. `ETLPipeline.bronze_to_silver()` is a full refresh per table (DELETE then re-INSERT from bronze) driven by the SQL files in `src/shopping_list/query/*.sql` — edit the `.sql` files to change aggregation logic, not Python.

`ETLPipeline.run_pipeline()` chains raw→bronze→bronze→silver and is called after every new ingestion (`ingest_to_raw` in the Streamlit app) and once at startup for legacy migration (`migrate_legacy_data`, one-shot: no-ops once `raw_purchases` has any rows).

### Shared loaders and analytics

- `src/shopping_list/loaders.py`: `load_product_stats`, `load_market_stats`, `load_monthly_spending` (Silver) and `load_bronze_data` (Bronze); each swallows exceptions and returns an empty DataFrame if the table doesn't exist yet (fresh install). The "needs to buy" flag (`buy`) is `days_last_purchase > avg_days_purchase`, computed in `load_product_stats`.
- `src/shopping_list/analytics.py`: `pct_change`, `compute_price_alerts`, `compute_recurrence_curve` and `market_color` (deterministic per-market color used by both apps).

### Streamlit app (`app/streamlit/src/shopping_list_streamlit/app.py`)

Single-file Streamlit app, organized as one function per tab, all wired up in `main()`:
- Tabs: Lista de Compras, Análise de Preços, Mercados, Tendências, Importar Dados, Editar Dados (`tab_shopping_list`, `tab_price_analysis`, `tab_market_analysis`, `tab_monthly_trends`, `tab_import_data`, `tab_edit_data`).
- Tendências also renders the purchase-recurrence curve (`render_recurrence_curve` / `compute_recurrence_curve`): an ECDF of days between consecutive purchases of the same product, one line for "Total" and one per market, computed in pandas from `load_bronze_data` (no Silver table).
- Import flow writes directly to `raw_purchases` via `ingest_to_raw`, then calls `ETLPipeline.run_pipeline()` and `st.rerun()`.

### Dash app (`app/dash/src/shopping_list_dash/`)

Read-only, English, dark theme. `create_app(loader=None)` takes an injectable loader returning `views.DashboardData` (default: MySQL via `data.load_from_database`, cached 30 s; DB errors become a banner instead of an exception). Header KPIs + four `dcc.Tabs` (Shopping list, Prices, Markets, Trends) rendered lazily by one callback. All numbers come from `views.py` (framework-free); all charts from `figures.py` through `theme.plotly_layout()`; values are formatted by `formatting.py` (`brl`, `pct`, `month_label`, ISO dates). Styling lives in `assets/style.css` (including `--Dash-*` variable overrides for dark dropdowns).

### Gemini OCR extraction (`src/shopping_list/gemini.py`)

`generate(prompt, img_bytes, mime_type)` sends a receipt image + prompt to `gemini-3.1-flash-lite` and expects strict JSON back (`response_mime_type="application/json"`). The prompt template lives in `docs/template/prompt.md` and is formatted with two placeholders before sending:
- `{products}` — newline-joined list of known `product_id`s (from Silver stats, or from the OCR response itself if Silver is empty) so the model normalizes new items against existing product names.
- `{response}` — the expected JSON shape, taken from `docs/template/response.json`.

The model returns eight keys per item — `purchase_date`, `product_id`, `quantity`, `unit_price`, `product_price` (line total), `market_id`, plus the receipt-level `access_key` (NFC-e chave de acesso) and `nfce_url` (QR-code URL), repeated on every item. The JSON response is parsed into a DataFrame, normalized by `ensure_ocr_columns`, and shown via an editable `st.data_editor`; the **edited** frame (not the raw model output) is what `ingest_to_raw` commits.

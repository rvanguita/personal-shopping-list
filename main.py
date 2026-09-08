# %%
import json
import time
import unicodedata
import zlib
from datetime import UTC, datetime

import altair as alt
import pandas as pd
import sqlalchemy
import streamlit as st

from src.database import DatabaseManager
from src.etl import ETLPipeline
from src.gemini import generate

# =============================================================================
# Inicialização
# =============================================================================


@st.cache_resource
def get_db_manager() -> DatabaseManager:
    """Inicializa o DatabaseManager (singleton via cache)."""
    db = DatabaseManager()
    db.create_all_tables()
    db.migrate_schema()
    return db


@st.cache_resource
def run_migration(_db: DatabaseManager):
    """Executa migração de dados legados uma única vez."""
    etl = ETLPipeline(_db)
    migrated = etl.migrate_legacy_data()
    if migrated > 0:
        etl.run_pipeline()
    return migrated


@st.cache_resource(ttl="10min")
def gemini_assistent(response, prompt, df_stats, open_img):
    if df_stats.empty:
        known_products = [item["product_id"] for item in response]
    else:
        known_products = df_stats["product_id"].tolist()

    products_ref = "\n".join(f"- {p}" for p in sorted({p for p in known_products if p}))
    response_ref = json.dumps(response, ensure_ascii=False, indent=2)
    prompt_exec = prompt.replace("{products}", products_ref).replace(
        "{response}", response_ref
    )

    resp = generate(prompt_exec, open_img.getvalue(), open_img.type)
    df = pd.DataFrame(json.loads(resp.text))
    return df


def read_file(path: str, json_file: bool = False):
    with open(path, "r") as f:
        if json_file:
            return json.load(f)
        return f.read()


# =============================================================================
# Data Loading (from Silver/Bronze layers)
# =============================================================================


def load_product_stats(db: DatabaseManager) -> pd.DataFrame:
    """Carrega estatísticas de produtos da camada Silver."""
    try:
        df = pd.read_sql("SELECT * FROM silver_product_stats", con=db.engine("silver"))
        if not df.empty:
            numeric_cols = [
                "avg_days_purchase",
                "avg_product_price",
                "min_product_price",
                "max_product_price",
                "days_last_purchase",
            ]
            df[numeric_cols] = df[numeric_cols].astype(float)
            df["buy"] = df["days_last_purchase"] > df["avg_days_purchase"]
        return df
    except Exception:  # noqa: BLE001
        return pd.DataFrame()


def load_market_stats(db: DatabaseManager) -> pd.DataFrame:
    """Carrega estatísticas de mercados da camada Silver."""
    try:
        df = pd.read_sql("SELECT * FROM silver_market_stats", con=db.engine("silver"))
        if not df.empty:
            df[["total_spent", "avg_ticket"]] = df[
                ["total_spent", "avg_ticket"]
            ].astype(float)
        return df
    except Exception:  # noqa: BLE001
        return pd.DataFrame()


def load_monthly_spending(db: DatabaseManager) -> pd.DataFrame:
    """Carrega gastos mensais da camada Silver."""
    try:
        df = pd.read_sql(
            "SELECT * FROM silver_monthly_spending", con=db.engine("silver")
        )
        if not df.empty:
            df[["total_spent", "avg_price"]] = df[["total_spent", "avg_price"]].astype(
                float
            )
        return df
    except Exception:  # noqa: BLE001
        return pd.DataFrame()


def load_bronze_data(db: DatabaseManager) -> pd.DataFrame:
    """Carrega dados da camada Bronze para análises detalhadas."""
    try:
        df = pd.read_sql(
            "SELECT purchase_date, product_id, product_price, market_id "
            "FROM bronze_purchases ORDER BY purchase_date",
            con=db.engine("bronze"),
        )
        if not df.empty:
            df["product_price"] = df["product_price"].astype(float)
        return df
    except Exception:  # noqa: BLE001
        return pd.DataFrame()


_BRONZE_EDIT_COLUMNS = [
    "id",
    "purchase_date",
    "product_id",
    "quantity",
    "unit_price",
    "product_price",
    "market_id",
    "access_key",
    "nfce_url",
]


def load_bronze_editable(db: DatabaseManager) -> pd.DataFrame:
    """Carrega bronze_purchases (com id) para edição manual."""
    try:
        df = pd.read_sql(
            "SELECT id, purchase_date, product_id, quantity, unit_price, "
            "product_price, market_id, access_key, nfce_url "
            "FROM bronze_purchases ORDER BY purchase_date DESC, id DESC",
            con=db.engine("bronze"),
        )
        if not df.empty:
            df["purchase_date"] = pd.to_datetime(df["purchase_date"]).dt.date
            for col in ("quantity", "unit_price", "product_price"):
                df[col] = df[col].astype(float)
        return df
    except Exception:  # noqa: BLE001
        return pd.DataFrame(columns=_BRONZE_EDIT_COLUMNS)


def purchase_column_config(include_id: bool = False) -> dict:
    """Configuração de colunas compartilhada pelos editores de compras."""
    config = {
        "purchase_date": st.column_config.DateColumn(
            "Data da compra", format="DD/MM/YYYY"
        ),
        "product_id": st.column_config.TextColumn("Produto"),
        "quantity": st.column_config.NumberColumn("Qtd", format="%.3f", min_value=0.0),
        "unit_price": st.column_config.NumberColumn(
            "Custo unit. (R$)", format="R$ %.2f", min_value=0.0
        ),
        "product_price": st.column_config.NumberColumn(
            "Total (R$)", format="R$ %.2f", min_value=0.0
        ),
        "market_id": st.column_config.TextColumn("Mercado"),
        "access_key": st.column_config.TextColumn("Chave de acesso", width="medium"),
        "nfce_url": st.column_config.TextColumn("URL NFC-e", width="large"),
    }
    if include_id:
        config = {"id": st.column_config.NumberColumn("ID", disabled=True), **config}
    return config


_OCR_COLUMNS = [
    "purchase_date",
    "product_id",
    "quantity",
    "unit_price",
    "product_price",
    "market_id",
    "access_key",
    "nfce_url",
]


def ensure_ocr_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Garante as colunas esperadas na resposta do OCR e as reordena."""
    df = df.copy()
    for col in _OCR_COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA
    # purchase_date precisa ser date (não string) para o DateColumn do
    # st.data_editor; valor inválido/ausente vira vazio para o usuário ajustar.
    df["purchase_date"] = pd.to_datetime(df["purchase_date"], errors="coerce").dt.date
    for col in ("quantity", "unit_price", "product_price"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    extra = [c for c in df.columns if c not in _OCR_COLUMNS]
    return df[[*_OCR_COLUMNS, *extra]]


# =============================================================================
# Insights — helpers de cálculo
# =============================================================================

_MESES_PT = {
    "01": "Janeiro",
    "02": "Fevereiro",
    "03": "Março",
    "04": "Abril",
    "05": "Maio",
    "06": "Junho",
    "07": "Julho",
    "08": "Agosto",
    "09": "Setembro",
    "10": "Outubro",
    "11": "Novembro",
    "12": "Dezembro",
}


def format_year_month(year_month: str) -> str:
    """Formata 'YYYY-MM' como 'Mês/YYYY'."""
    year, month = year_month.split("-")
    return f"{_MESES_PT.get(month, month)}/{year}"


def pct_change(current: float, previous: float | None) -> float | None:
    """Variação percentual de `previous` para `current`, ou None se não houver base."""
    if not previous:
        return None
    return (current - previous) / previous


def compute_price_alerts(
    df_bronze: pd.DataFrame, threshold: float = 0.15
) -> pd.DataFrame:
    """Produtos cujo último preço registrado subiu mais que `threshold` frente à média anterior."""
    if df_bronze.empty:
        return pd.DataFrame()

    alerts = []
    for product_id, group in df_bronze.sort_values("purchase_date").groupby(
        "product_id"
    ):
        if len(group) < 2:
            continue
        last_price = group["product_price"].iloc[-1]
        prior_avg = group["product_price"].iloc[:-1].mean()
        variation = pct_change(last_price, prior_avg)
        if variation is not None and variation > threshold:
            alerts.append(
                {
                    "product_id": product_id,
                    "last_price": last_price,
                    "prior_avg_price": prior_avg,
                    "variation_pct": variation,
                    "last_purchase_date": group["purchase_date"].iloc[-1],
                }
            )

    if not alerts:
        return pd.DataFrame()
    return pd.DataFrame(alerts).sort_values("variation_pct", ascending=False)


def _recurrence_gap_frame(df: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """Linhas de compra com a coluna `gap` = dias desde a compra anterior
    (do mesmo grupo `keys`). Primeira compra de cada grupo é descartada."""
    ordered = df.sort_values([*keys, "purchase_date"]).copy()
    ordered["gap"] = ordered.groupby(keys, sort=False)["purchase_date"].diff().dt.days
    ordered = ordered.dropna(subset=["gap"])
    return ordered[ordered["gap"] >= 0]


def compute_recurrence_curve(
    df_bronze: pd.DataFrame, max_days: int = 60
) -> pd.DataFrame:
    """ECDF do intervalo entre compras consecutivas do mesmo produto.

    Formato longo: `scope` ("Total" ou nome do mercado), `days` (0..max_days) e
    `cumulative_pct` (fração das recompras já ocorridas até aquele dia).
    """
    cols = ["scope", "days", "cumulative_pct"]
    if df_bronze.empty:
        return pd.DataFrame(columns=cols)

    df = df_bronze.copy()
    df["purchase_date"] = pd.to_datetime(df["purchase_date"])

    series: dict[str, pd.Series] = {
        "Total": _recurrence_gap_frame(df, ["product_id"])["gap"]
    }
    by_market = _recurrence_gap_frame(df, ["market_id", "product_id"])
    for market, grp in by_market.groupby("market_id"):
        series[market] = grp["gap"]

    rows = []
    for scope, gaps in series.items():
        if gaps.empty:
            continue
        n = len(gaps)
        rows += [
            {"scope": scope, "days": d, "cumulative_pct": (gaps <= d).sum() / n}
            for d in range(max_days + 1)
        ]
    return pd.DataFrame(rows, columns=cols)


# =============================================================================
# Cor por mercado — código de cor consistente nos gráficos
# =============================================================================

# Tokens de cor do tema (.streamlit/config.toml)
_MARKET_FIXED_COLORS = {"swift": "#F59E0B", "atacadao": "#22C55E"}
_TOTAL_COLOR = "#94A3B8"  # grayColor
_MARKET_FALLBACK_PALETTE = ["#3B82F6", "#38BDF8", "#8B5CF6", "#EF4444", "#14B8A6"]


def _norm_market(name: str) -> str:
    """Normaliza nome de mercado: sem acento, sem espaços nas pontas, minúsculo."""
    ascii_name = (
        unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    )
    return ascii_name.strip().lower()


def market_color(name: str) -> str:
    """Cor determinística de um mercado (ou de 'Total').

    Swift/Atacadão têm cor fixa; os demais recebem uma cor estável derivada do
    nome (crc32 → paleta), então não muda entre reruns nem sessões.
    """
    if str(name) == "Total":
        return _TOTAL_COLOR
    key = _norm_market(name)
    if key in _MARKET_FIXED_COLORS:
        return _MARKET_FIXED_COLORS[key]
    idx = zlib.crc32(key.encode()) % len(_MARKET_FALLBACK_PALETTE)
    return _MARKET_FALLBACK_PALETTE[idx]


def market_color_scale(names) -> alt.Scale:
    """`alt.Scale` que fixa cada nome (mercado ou 'Total') na sua cor."""
    domain = list(dict.fromkeys(str(n) for n in names))
    return alt.Scale(domain=domain, range=[market_color(n) for n in domain])


# =============================================================================
# KPIs — Resumo Geral (topo da página)
# =============================================================================


def render_kpi_row(
    df_products: pd.DataFrame,
    df_markets: pd.DataFrame,
    df_monthly: pd.DataFrame,
):
    if df_monthly.empty and df_products.empty:
        st.info(
            "Nenhum dado disponível ainda. Importe dados na aba "
            "**Importar dados** para começar.",
            icon=":material/info:",
        )
        return

    with st.container(horizontal=True):
        if not df_monthly.empty:
            df_monthly_sorted = df_monthly.sort_values("year_month")
            total_gasto = float(df_monthly_sorted["total_spent"].sum())
            current_spent = float(df_monthly_sorted["total_spent"].iloc[-1])
            previous_spent = (
                float(df_monthly_sorted["total_spent"].iloc[-2])
                if len(df_monthly_sorted) > 1
                else None
            )
            variation = pct_change(current_spent, previous_spent)
            st.metric(
                "Total gasto",
                f"R$ {total_gasto:,.2f}",
                delta=f"{variation:+.1%} vs. mês anterior"
                if variation is not None
                else None,
                delta_color="inverse",
                border=True,
                chart_data=df_monthly_sorted["total_spent"].tolist(),
                chart_type="bar",
            )

        if not df_products.empty:
            top_row = df_products.loc[df_products["total_purchases"].idxmax()]
            st.metric(
                "Produto mais comprado",
                top_row["product_id"],
                f"{int(top_row['total_purchases'])} compras",
                delta_color="off",
                border=True,
            )

        if not df_markets.empty:
            top_market = df_markets.loc[df_markets["visit_count"].idxmax()]
            st.metric(
                "Mercado favorito",
                top_market["market_id"],
                f"{int(top_market['visit_count'])} visitas",
                delta_color="off",
                border=True,
            )

        if not df_products.empty:
            min_days = float(df_products["days_last_purchase"].min())
            st.metric(
                "Última compra",
                f"{min_days:.0f} dias atrás",
                border=True,
            )


# =============================================================================
# Sidebar
# =============================================================================


def render_sidebar():
    with st.sidebar:
        st.caption("Dados atualizados automaticamente após cada importação.")
        if st.button("Atualizar dados", icon=":material/refresh:", width="stretch"):
            st.cache_resource.clear()
            st.rerun()


# =============================================================================
# Aba 1 — Lista de Compras
# =============================================================================


def tab_shopping_list(df_products: pd.DataFrame):
    st.subheader("Lista de compras inteligente")
    st.caption("Produtos que você pode precisar comprar, baseado no histórico.")

    if df_products.empty:
        st.warning("Nenhum dado disponível. Importe dados na aba **Importar dados**.")
        return

    col1, col2, col3 = st.columns([2, 2, 1])
    filter_days = col1.number_input(
        "Dias sem retornar ao mercado",
        min_value=1,
        max_value=90,
        value=30,
        step=1,
    )
    show_all = col2.checkbox("Mostrar todos os produtos")
    col3.metric("A comprar", int(df_products["buy"].sum()), border=True)

    if show_all:
        df_display = df_products.copy()
    else:
        df_display = df_products[
            df_products["days_last_purchase"] <= filter_days
        ].copy()

    if df_display.empty:
        st.info("Nenhum produto encontrado para o filtro selecionado.")
        return

    df_display = df_display.sort_values(
        ["buy", "days_last_purchase"], ascending=[False, False]
    )

    # Progresso até a próxima compra esperada (100% = no prazo médio, >100% = atrasado)
    avg_days = df_display["avg_days_purchase"].mask(
        df_display["avg_days_purchase"] == 0
    )
    df_display["purchase_progress"] = (
        (df_display["days_last_purchase"] / avg_days * 100).clip(upper=150).fillna(0)
    )

    df_show = df_display[
        [
            "product_id",
            "days_last_purchase",
            "avg_days_purchase",
            "avg_product_price",
            "total_purchases",
            "last_purchase_date",
            "purchase_progress",
        ]
    ].rename(
        columns={
            "product_id": "Produto",
            "days_last_purchase": "Dias s/ comprar",
            "avg_days_purchase": "Média dias",
            "avg_product_price": "Preço médio (R$)",
            "total_purchases": "Total compras",
            "last_purchase_date": "Última compra",
            "purchase_progress": "Progresso até a próxima compra",
        }
    )

    st.dataframe(
        df_show,
        hide_index=True,
        column_config={
            "Progresso até a próxima compra": st.column_config.ProgressColumn(
                "Progresso até a próxima compra",
                format="%.0f%%",
                min_value=0,
                max_value=150,
            ),
            "Preço médio (R$)": st.column_config.NumberColumn(
                "Preço médio (R$)",
                format="R$ %.2f",
            ),
            "Última compra": st.column_config.DateColumn(
                "Última compra",
                format="DD/MM/YYYY",
            ),
        },
    )


# =============================================================================
# Aba 2 — Análise de Preços
# =============================================================================


def tab_price_analysis(df_products: pd.DataFrame, df_bronze: pd.DataFrame):
    st.subheader("Análise de preços")

    if df_products.empty or df_bronze.empty:
        st.warning("Nenhum dado disponível para análise de preços.")
        return

    st.markdown("**Resumo de preços por produto**")
    df_prices = df_products[
        [
            "product_id",
            "avg_product_price",
            "min_product_price",
            "max_product_price",
            "total_purchases",
        ]
    ].copy()

    df_prices["variacao"] = (
        df_prices["max_product_price"] - df_prices["min_product_price"]
    )
    df_prices = df_prices.sort_values("variacao", ascending=False)

    st.dataframe(
        df_prices.rename(
            columns={
                "product_id": "Produto",
                "avg_product_price": "Preço médio (R$)",
                "min_product_price": "Menor preço (R$)",
                "max_product_price": "Maior preço (R$)",
                "total_purchases": "Compras",
                "variacao": "Variação (R$)",
            }
        ),
        hide_index=True,
        column_config={
            "Preço médio (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
            "Menor preço (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
            "Maior preço (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
            "Variação (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
        },
    )

    with st.container(border=True):
        st.markdown("**Alertas de aumento de preço**")
        df_alerts = compute_price_alerts(df_bronze)
        if df_alerts.empty:
            st.caption(
                "Nenhuma alta de preço relevante identificada no último "
                "registro de cada produto."
            )
        else:
            st.dataframe(
                df_alerts.rename(
                    columns={
                        "product_id": "Produto",
                        "last_price": "Preço atual (R$)",
                        "prior_avg_price": "Média anterior (R$)",
                        "variation_pct": "Variação",
                        "last_purchase_date": "Data",
                    }
                ),
                hide_index=True,
                column_config={
                    "Preço atual (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
                    "Média anterior (R$)": st.column_config.NumberColumn(
                        format="R$ %.2f"
                    ),
                    "Variação": st.column_config.NumberColumn(format="percent"),
                    "Data": st.column_config.DateColumn(format="DD/MM/YYYY"),
                },
            )

    st.markdown("**Evolução de preço por produto**")
    products = sorted(df_bronze["product_id"].unique())
    selected_products = st.multiselect(
        "Selecione os produtos para comparar",
        products,
        default=products[:3] if len(products) >= 3 else products,
    )

    if selected_products:
        df_filtered = df_bronze[df_bronze["product_id"].isin(selected_products)].copy()
        df_filtered["purchase_date"] = pd.to_datetime(df_filtered["purchase_date"])

        chart = (
            alt.Chart(df_filtered)
            .mark_line(point=True)
            .encode(
                x=alt.X("purchase_date:T", title="Data da compra"),
                y=alt.Y("product_price:Q", title="Preço (R$)"),
                color=alt.Color("product_id:N", title="Produto"),
                tooltip=[
                    alt.Tooltip("product_id:N", title="Produto"),
                    alt.Tooltip("purchase_date:T", title="Data", format="%d/%m/%Y"),
                    alt.Tooltip("product_price:Q", title="Preço (R$)", format=".2f"),
                ],
            )
        )
        st.altair_chart(chart)
    else:
        st.caption("Selecione pelo menos um produto para ver a evolução de preço.")


# =============================================================================
# Aba 3 — Análise por Mercado
# =============================================================================


def tab_market_analysis(df_markets: pd.DataFrame):
    st.subheader("Análise por mercado")

    if df_markets.empty:
        st.warning("Nenhum dado disponível para análise de mercados.")
        return

    total_spent_all = float(df_markets["total_spent"].sum())
    total_visits_all = int(df_markets["visit_count"].sum())
    avg_ticket_all = total_spent_all / total_visits_all if total_visits_all else 0.0
    top_market = df_markets.loc[df_markets["visit_count"].idxmax(), "market_id"]

    with st.container(horizontal=True):
        st.metric("Total gasto em mercados", f"R$ {total_spent_all:,.2f}", border=True)
        st.metric("Ticket médio geral", f"R$ {avg_ticket_all:,.2f}", border=True)
        st.metric("Mercado mais visitado", top_market, delta_color="off", border=True)

    col1, col2 = st.columns(2)

    with col1, st.container(border=True):
        st.markdown("**Gasto total por mercado**")
        df_sorted = df_markets.sort_values("total_spent", ascending=False)
        chart = (
            alt.Chart(df_sorted)
            .mark_bar()
            .encode(
                x=alt.X("total_spent:Q", title="Total gasto (R$)"),
                y=alt.Y("market_id:N", title="Mercado", sort="-x"),
                color=alt.Color(
                    "market_id:N",
                    scale=market_color_scale(df_sorted["market_id"]),
                    legend=None,
                ),
                tooltip=[
                    alt.Tooltip("market_id:N", title="Mercado"),
                    alt.Tooltip(
                        "total_spent:Q", title="Total gasto (R$)", format=".2f"
                    ),
                ],
            )
        )
        st.altair_chart(chart)

    with col2, st.container(border=True):
        st.markdown("**Ticket médio por mercado**")
        df_sorted_ticket = df_markets.sort_values("avg_ticket", ascending=False)
        chart = (
            alt.Chart(df_sorted_ticket)
            .mark_bar()
            .encode(
                x=alt.X("avg_ticket:Q", title="Ticket médio (R$)"),
                y=alt.Y("market_id:N", title="Mercado", sort="-x"),
                color=alt.Color(
                    "market_id:N",
                    scale=market_color_scale(df_sorted_ticket["market_id"]),
                    legend=None,
                ),
                tooltip=[
                    alt.Tooltip("market_id:N", title="Mercado"),
                    alt.Tooltip(
                        "avg_ticket:Q", title="Ticket médio (R$)", format=".2f"
                    ),
                ],
            )
        )
        st.altair_chart(chart)

    st.markdown("**Detalhamento**")
    st.dataframe(
        df_markets.rename(
            columns={
                "market_id": "Mercado",
                "total_spent": "Total gasto (R$)",
                "avg_ticket": "Ticket médio (R$)",
                "visit_count": "Visitas",
                "last_visit": "Última visita",
            }
        ),
        hide_index=True,
        column_config={
            "Total gasto (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
            "Ticket médio (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
            "Última visita": st.column_config.DateColumn(format="DD/MM/YYYY"),
        },
    )


# =============================================================================
# Aba 4 — Tendências Mensais
# =============================================================================


def tab_monthly_trends(df_monthly: pd.DataFrame, df_bronze: pd.DataFrame):
    st.subheader("Tendências mensais")

    if df_monthly.empty:
        st.warning("Nenhum dado disponível para análise de tendências.")
        return

    df_monthly_sorted = df_monthly.sort_values("year_month").reset_index(drop=True)
    current = df_monthly_sorted.iloc[-1]
    previous = df_monthly_sorted.iloc[-2] if len(df_monthly_sorted) > 1 else None

    col1, col2, col3 = st.columns(3)
    col1.metric(
        f"Gasto em {format_year_month(current['year_month'])}",
        f"R$ {current['total_spent']:,.2f}",
        delta=(
            f"{pct_change(current['total_spent'], previous['total_spent']):+.1%} vs. mês anterior"
            if previous is not None
            else None
        ),
        delta_color="inverse",
    )
    col2.metric(
        "Itens no mês",
        int(current["item_count"]),
        delta=(
            f"{pct_change(current['item_count'], previous['item_count']):+.1%} vs. mês anterior"
            if previous is not None
            else None
        ),
        delta_color="off",
    )
    col3.metric(
        "Preço médio",
        f"R$ {current['avg_price']:,.2f}",
        delta=(
            f"{pct_change(current['avg_price'], previous['avg_price']):+.1%} vs. mês anterior"
            if previous is not None
            else None
        ),
        delta_color="inverse",
    )

    st.markdown("**Gastos mensais**")
    chart = (
        alt.Chart(df_monthly_sorted)
        .mark_bar()
        .encode(
            x=alt.X("year_month:O", title="Mês"),
            y=alt.Y("total_spent:Q", title="Total gasto (R$)"),
            tooltip=[
                alt.Tooltip("year_month:O", title="Mês"),
                alt.Tooltip("total_spent:Q", title="Total gasto (R$)", format=".2f"),
            ],
        )
    )
    st.altair_chart(chart)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Itens por mês**")
        chart = (
            alt.Chart(df_monthly_sorted)
            .mark_bar()
            .encode(
                x=alt.X("year_month:O", title="Mês"),
                y=alt.Y("item_count:Q", title="Itens"),
                tooltip=[
                    alt.Tooltip("year_month:O", title="Mês"),
                    alt.Tooltip("item_count:Q", title="Itens"),
                ],
            )
        )
        st.altair_chart(chart)

    with col2:
        st.markdown("**Preço médio por mês**")
        chart = (
            alt.Chart(df_monthly_sorted)
            .mark_line(point=True)
            .encode(
                x=alt.X("year_month:O", title="Mês"),
                y=alt.Y("avg_price:Q", title="Preço médio (R$)"),
                tooltip=[
                    alt.Tooltip("year_month:O", title="Mês"),
                    alt.Tooltip("avg_price:Q", title="Preço médio (R$)", format=".2f"),
                ],
            )
        )
        st.altair_chart(chart)

    st.markdown("**Detalhamento mensal**")
    st.dataframe(
        df_monthly.rename(
            columns={
                "year_month": "Mês",
                "total_spent": "Total gasto (R$)",
                "item_count": "Itens",
                "avg_price": "Preço médio (R$)",
            }
        ).sort_values("Mês", ascending=False),
        hide_index=True,
        column_config={
            "Total gasto (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
            "Preço médio (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
        },
    )

    render_recurrence_curve(df_bronze)


def render_recurrence_curve(df_bronze: pd.DataFrame):
    """Curva de recorrência de compra (ECDF do intervalo entre recompras)."""
    st.markdown("**Curva de recorrência de compra**")
    st.caption(
        "Fração das recompras já realizadas conforme os dias passados desde a "
        "compra anterior do mesmo produto. Ex.: 50% em 14 dias = metade das "
        "recompras acontece em até duas semanas."
    )

    df_curve = compute_recurrence_curve(df_bronze)
    if df_curve.empty:
        st.info("Ainda não há recompras suficientes para traçar a curva.")
        return

    scopes = df_curve["scope"].unique().tolist()
    market_scopes = [s for s in scopes if s != "Total"]
    market_order = (
        df_bronze["market_id"].value_counts().index.tolist()
        if not df_bronze.empty
        else []
    )
    top_markets = [m for m in market_order if m in market_scopes][:3]
    default_scopes = [s for s in ["Total", *top_markets] if s in scopes]

    selected = st.multiselect(
        "Escopos para comparar",
        scopes,
        default=default_scopes,
    )
    if not selected:
        st.caption("Selecione pelo menos um escopo para ver a curva.")
        return

    df_sel = df_curve[df_curve["scope"].isin(selected)]
    chart = (
        alt.Chart(df_sel)
        .mark_line(interpolate="step-after")
        .encode(
            x=alt.X("days:Q", title="Dias desde a compra anterior"),
            y=alt.Y(
                "cumulative_pct:Q",
                title="% das recompras",
                axis=alt.Axis(format="%"),
            ),
            color=alt.Color(
                "scope:N",
                title="Escopo",
                scale=market_color_scale(df_sel["scope"]),
            ),
            tooltip=[
                alt.Tooltip("scope:N", title="Escopo"),
                alt.Tooltip("days:Q", title="Dias"),
                alt.Tooltip("cumulative_pct:Q", title="% recomprado", format=".0%"),
            ],
        )
    )
    st.altair_chart(chart)


# =============================================================================
# Aba 5 — Importar Dados
# =============================================================================


def ingest_to_raw(db: DatabaseManager, df: pd.DataFrame, source_type: str):
    """Insere dados na camada Raw e executa o pipeline ETL."""
    raw_engine = db.engine("raw")

    df = df.copy()
    # product_price é o total da linha; se vier só quantidade + custo unitário,
    # completa aqui para não violar o NOT NULL de raw_purchases.product_price.
    if "product_price" not in df.columns and {"quantity", "unit_price"} <= set(
        df.columns
    ):
        df["product_price"] = pd.to_numeric(
            df["quantity"], errors="coerce"
        ) * pd.to_numeric(df["unit_price"], errors="coerce")

    df_raw = pd.DataFrame()
    df_raw["purchase_date"] = df["purchase_date"].astype(str)
    df_raw["product_id"] = df["product_id"].astype(str)
    df_raw["product_price"] = df["product_price"].astype(str)
    for col in ("quantity", "unit_price"):
        df_raw[col] = df[col].astype(str) if col in df.columns else ""
    df_raw["market_id"] = df["market_id"].astype(str)
    # Metadados da NFC-e (opcionais): NaN -> "" para não gravar "nan".
    for col in ("access_key", "nfce_url"):
        df_raw[col] = df[col].fillna("").astype(str) if col in df.columns else ""
    df_raw["ingested_at"] = datetime.now(tz=UTC)
    df_raw["source_type"] = source_type

    df_raw.to_sql(
        "raw_purchases",
        con=raw_engine,
        if_exists="append",
        index=False,
    )

    # Executar ETL pipeline
    etl = ETLPipeline(db)
    etl.run_pipeline()


def tab_import_data(db: DatabaseManager, df_products: pd.DataFrame):
    st.subheader("Importar dados")

    tab_img, tab_csv = st.tabs(
        [
            ":material/photo_camera: Nota fiscal (OCR)",
            ":material/description: Arquivo CSV",
        ]
    )

    with tab_img:
        st.markdown("**Upload de nota fiscal**")
        st.caption("Envie uma imagem de nota fiscal para extração automática via IA.")

        open_img = st.file_uploader(
            "Upload da imagem da nota fiscal",
            type=["jpg", "jpeg", "png"],
        )

        if open_img:
            response = read_file("template/response.json", json_file=True)
            prompt = read_file("template/prompt.md")

            st.image(open_img, caption="Imagem enviada para o Gemini...")
            df = ensure_ocr_columns(
                gemini_assistent(response, prompt, df_products, open_img)
            )
            edited = st.data_editor(
                df,
                num_rows="dynamic",
                hide_index=True,
                key="ocr_editor",
                column_config=purchase_column_config(),
            )

            if st.button("Importar dados", icon=":material/upload:", key="tax_invoice"):
                time.sleep(1)
                try:
                    ingest_to_raw(db, edited, source_type="ocr")
                    st.success(
                        "Dados importados e processados com sucesso!",
                        icon=":material/check_circle:",
                    )
                    st.cache_resource.clear()
                    st.rerun()
                except Exception as e:  # noqa: BLE001
                    st.error(f"Erro ao importar: {e}", icon=":material/error:")

    with tab_csv:
        st.markdown("**Upload de CSV**")
        st.caption(
            "Colunas obrigatórias: `purchase_date`, `product_id`, `market_id` e "
            "`product_price` **ou** (`quantity` + `unit_price`). "
            "`quantity` (padrão 1) e `unit_price` são opcionais quando "
            "`product_price` já vem preenchido. `access_key` e `nfce_url` "
            "(dados da NFC-e) também são opcionais."
        )

        open_file = st.file_uploader("Upload do arquivo CSV", type=["csv"])

        if open_file is not None:
            df = pd.read_csv(open_file)
            st.dataframe(df, hide_index=True)

            if st.button("Importar dados", icon=":material/upload:", key="csv_import"):
                try:
                    ingest_to_raw(db, df, source_type="csv")
                    st.success(
                        "Dados importados e processados com sucesso!",
                        icon=":material/check_circle:",
                    )
                    st.cache_resource.clear()
                    st.rerun()
                except Exception as e:  # noqa: BLE001
                    st.error(f"Erro ao importar: {e}", icon=":material/error:")


# =============================================================================
# Aba 6 — Editar Dados
# =============================================================================


def save_bronze_edits(
    db: DatabaseManager, df_original: pd.DataFrame, df_edited: pd.DataFrame
) -> dict[str, int]:
    """Aplica inclusões/edições/exclusões feitas no editor à camada Bronze.

    Opera direto em `bronze_purchases` (a `raw_to_bronze` é incremental e nunca
    reprocessa linhas existentes), e no fim recarrega a camada Silver.
    """
    bronze_engine = db.engine("bronze")
    counts = {"inserted": 0, "updated": 0, "deleted": 0}

    original_by_id = {int(r.id): r for r in df_original.itertuples(index=False)}
    edited_ids = {
        int(r.id) for r in df_edited.itertuples(index=False) if not pd.isna(r.id)
    }
    deleted_ids = set(original_by_id) - edited_ids

    def clean(value: object) -> str:
        return str(value).strip().title()

    def meta(value: object) -> str | None:
        """Metadado de texto (chave NFC-e / URL): strip, vazio -> None."""
        s = "" if pd.isna(value) else str(value).strip()
        return s or None

    def is_blank(row) -> bool:
        has_price = not pd.isna(row.product_price) or (
            not pd.isna(row.quantity) and not pd.isna(row.unit_price)
        )
        return (
            pd.isna(row.purchase_date)
            or not has_price
            or not str(row.product_id).strip()
            or not str(row.market_id).strip()
        )

    def reconcile(row) -> tuple[float, float, float]:
        """(quantidade, custo unitário, total). product_price = total da linha."""
        qty = 0.0 if pd.isna(row.quantity) else float(row.quantity)
        if qty <= 0:
            qty = 1.0
        total = None if pd.isna(row.product_price) else float(row.product_price)
        unit = None if pd.isna(row.unit_price) else float(row.unit_price)
        if unit is None and total is not None:
            unit = total / qty
        if total is None and unit is not None:
            total = unit * qty
        return round(qty, 3), round(unit, 2), round(total, 2)

    with bronze_engine.begin() as conn:
        for del_id in deleted_ids:
            conn.execute(
                sqlalchemy.text("DELETE FROM bronze_purchases WHERE id = :id"),
                {"id": int(del_id)},
            )
            counts["deleted"] += 1

        for row in df_edited.itertuples(index=False):
            now = datetime.now(tz=UTC)

            if pd.isna(row.id):
                if is_blank(row):
                    continue
                qty, unit, total = reconcile(row)
                conn.execute(
                    sqlalchemy.text(
                        "INSERT INTO bronze_purchases "
                        "(purchase_date, product_id, quantity, unit_price, "
                        "product_price, market_id, access_key, nfce_url, "
                        "raw_id, processed_at) "
                        "VALUES (:date, :product, :qty, :unit, :price, :market, "
                        ":akey, :nurl, 0, :ts)"
                    ),
                    {
                        "date": row.purchase_date,
                        "product": clean(row.product_id),
                        "qty": qty,
                        "unit": unit,
                        "price": total,
                        "market": clean(row.market_id),
                        "akey": meta(row.access_key),
                        "nurl": meta(row.nfce_url),
                        "ts": now,
                    },
                )
                counts["inserted"] += 1
                continue

            original = original_by_id[int(row.id)]
            unchanged = (
                str(original.purchase_date) == str(row.purchase_date)
                and str(original.product_id) == str(row.product_id)
                and float(original.quantity) == float(row.quantity)
                and float(original.unit_price) == float(row.unit_price)
                and float(original.product_price) == float(row.product_price)
                and str(original.market_id) == str(row.market_id)
                and meta(original.access_key) == meta(row.access_key)
                and meta(original.nfce_url) == meta(row.nfce_url)
            )
            if unchanged or is_blank(row):
                continue

            qty, unit, total = reconcile(row)
            conn.execute(
                sqlalchemy.text(
                    "UPDATE bronze_purchases SET purchase_date = :date, "
                    "product_id = :product, quantity = :qty, unit_price = :unit, "
                    "product_price = :price, market_id = :market, "
                    "access_key = :akey, nfce_url = :nurl, "
                    "processed_at = :ts WHERE id = :id"
                ),
                {
                    "date": row.purchase_date,
                    "product": clean(row.product_id),
                    "qty": qty,
                    "unit": unit,
                    "price": total,
                    "market": clean(row.market_id),
                    "akey": meta(row.access_key),
                    "nurl": meta(row.nfce_url),
                    "ts": now,
                    "id": int(row.id),
                },
            )
            counts["updated"] += 1

    ETLPipeline(db).bronze_to_silver()
    return counts


def tab_edit_data(db: DatabaseManager):
    st.subheader("Editar dados manualmente")
    st.caption(
        "Edite, adicione ou remova compras direto na camada Bronze. "
        "As análises são recalculadas ao salvar."
    )

    df_bronze = load_bronze_editable(db)

    if df_bronze.empty:
        st.info(
            "Nenhum registro na camada Bronze ainda. Adicione linhas abaixo ou "
            "use a aba **Importar dados**.",
            icon=":material/info:",
        )

    edited = st.data_editor(
        df_bronze,
        num_rows="dynamic",
        hide_index=True,
        width="stretch",
        key="bronze_editor",
        column_config=purchase_column_config(include_id=True),
    )

    if st.button(
        "Salvar alterações", icon=":material/save:", type="primary", key="save_bronze"
    ):
        try:
            counts = save_bronze_edits(db, df_bronze, edited)
            if not any(counts.values()):
                st.info("Nenhuma alteração para salvar.", icon=":material/info:")
            else:
                st.success(
                    f"Alterações salvas: {counts['inserted']} incluída(s), "
                    f"{counts['updated']} atualizada(s), "
                    f"{counts['deleted']} removida(s).",
                    icon=":material/check_circle:",
                )
                st.cache_resource.clear()
                st.rerun()
        except Exception as e:  # noqa: BLE001
            st.error(f"Erro ao salvar: {e}", icon=":material/error:")


# =============================================================================
# Main
# =============================================================================


def main():
    st.set_page_config(
        page_title="Shopping List Intelligence",
        page_icon=":material/shopping_cart:",
        layout="wide",
    )

    # Inicialização
    db = get_db_manager()
    run_migration(db)

    # Carregar dados da camada Silver
    df_products = load_product_stats(db)
    df_markets = load_market_stats(db)
    df_monthly = load_monthly_spending(db)
    df_bronze = load_bronze_data(db)

    # Sidebar
    render_sidebar()

    # Header + KPIs
    st.title("Shopping List Intelligence")
    render_kpi_row(df_products, df_markets, df_monthly)

    # Tabs
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
        [
            ":material/shopping_cart: Lista de compras",
            ":material/trending_up: Análise de preços",
            ":material/storefront: Mercados",
            ":material/calendar_month: Tendências",
            ":material/upload_file: Importar dados",
            ":material/edit: Editar dados",
        ]
    )

    with tab1:
        tab_shopping_list(df_products)

    with tab2:
        tab_price_analysis(df_products, df_bronze)

    with tab3:
        tab_market_analysis(df_markets)

    with tab4:
        tab_monthly_trends(df_monthly, df_bronze)

    with tab5:
        tab_import_data(db, df_products)

    with tab6:
        tab_edit_data(db)


# %%
if __name__ == "__main__":
    main()

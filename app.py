import hashlib
import re
from typing import Dict, List, Optional

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(
    page_title="Flexible Site Mapping Tool",
    page_icon="🗺️",
    layout="wide",
)

REQUIRED_COLUMNS = ["site code", "lat", "long"]
MAX_DIMENSION_COLUMNS = 4
DEFAULT_SYMBOL_SEQUENCE = ["circle", "square", "diamond", "triangle", "cross"]
CONTINUOUS_COLOR_SCALES = ["Viridis", "Plasma", "Turbo", "Bluered", "RdYlGn", "Cividis", "Inferno", "Magma"]
DEFAULT_COLOR_PALETTE = [
    "#66c2a5", "#fc8d62", "#8da0cb", "#e78ac3", "#a6d854",
    "#ffd92f", "#e5c494", "#b3b3b3", "#1f77b4", "#ff7f0e",
    "#2ca02c", "#d62728", "#9467bd", "#8c564b", "#e377c2",
    "#7f7f7f", "#bcbd22", "#17becf",
]


def normalize_col_name(col: str) -> str:
    return str(col).strip().lower()


def find_required_column(df: pd.DataFrame, required_name: str) -> Optional[str]:
    normalized_map = {normalize_col_name(c): c for c in df.columns}
    aliases = {
        "site code": ["site code", "site_code", "site", "site id", "site_id", "store", "store number", "location id"],
        "lat": ["lat", "latitude"],
        "long": ["long", "lng", "lon", "longitude"],
    }
    for alias in aliases.get(required_name, [required_name]):
        if alias in normalized_map:
            return normalized_map[alias]
    return None


def clean_upload(df: pd.DataFrame):
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]

    required_mapping = {}
    missing = []
    for col in REQUIRED_COLUMNS:
        matched = find_required_column(df, col)
        if matched is None:
            missing.append(col)
        else:
            required_mapping[col] = matched

    if missing:
        return df, required_mapping, missing

    df[required_mapping["lat"]] = pd.to_numeric(df[required_mapping["lat"]], errors="coerce")
    df[required_mapping["long"]] = pd.to_numeric(df[required_mapping["long"]], errors="coerce")
    df = df.dropna(subset=[required_mapping["lat"], required_mapping["long"]])
    df[required_mapping["site code"]] = df[required_mapping["site code"]].astype(str)

    return df, required_mapping, []


def get_dimension_columns(df: pd.DataFrame, required_mapping: Dict[str, str]) -> List[str]:
    required_actual = set(required_mapping.values())
    dimensions = [c for c in df.columns if c not in required_actual]
    return dimensions[:MAX_DIMENSION_COLUMNS]


def is_categorical(series: pd.Series) -> bool:
    clean = series.dropna()
    if clean.empty:
        return True
    return (not pd.api.types.is_numeric_dtype(clean)) or clean.nunique() <= 20


def add_sidebar_filters(df: pd.DataFrame, site_col: str, dimension_cols: List[str]) -> pd.DataFrame:
    filtered = df.copy()
    st.sidebar.subheader("Filters")

    site_values = sorted(filtered[site_col].dropna().astype(str).unique().tolist())
    selected_sites = st.sidebar.multiselect(
        "Site code",
        options=site_values,
        default=site_values,
        help="Select one or more sites to include on the map.",
    )
    filtered = filtered[filtered[site_col].astype(str).isin(selected_sites)]

    for col in dimension_cols:
        if filtered.empty:
            break

        series = filtered[col]
        if pd.api.types.is_numeric_dtype(series) and series.dropna().nunique() > 10:
            min_val = float(series.min()) if not series.dropna().empty else 0.0
            max_val = float(series.max()) if not series.dropna().empty else 0.0
            if min_val == max_val:
                st.sidebar.caption(f"{col}: all visible values are {min_val:g}")
                continue
            selected_range = st.sidebar.slider(
                col,
                min_value=min_val,
                max_value=max_val,
                value=(min_val, max_val),
            )
            filtered = filtered[(filtered[col] >= selected_range[0]) & (filtered[col] <= selected_range[1])]
        else:
            values = sorted(series.fillna("[Blank]").astype(str).unique().tolist())
            selected_values = st.sidebar.multiselect(col, options=values, default=values)
            compare_series = filtered[col].fillna("[Blank]").astype(str)
            filtered = filtered[compare_series.isin(selected_values)]

    return filtered


def safe_widget_key(*parts: object) -> str:
    raw = "__".join(str(part) for part in parts)
    digest = hashlib.md5(raw.encode("utf-8")).hexdigest()
    return f"widget_{digest}"


def to_hex(color: object) -> str:
    if isinstance(color, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", color.strip()):
        return color.strip()
    return "#1f77b4"


def build_color_map(df: pd.DataFrame, color_col: str) -> Dict[str, str]:
    values = sorted(df[color_col].fillna("[Blank]").astype(str).unique().tolist())
    color_map = {}

    with st.sidebar.expander("Choose category colors", expanded=True):
        st.caption("Pick a color for each visible category.")
        for idx, value in enumerate(values):
            default_color = DEFAULT_COLOR_PALETTE[idx % len(DEFAULT_COLOR_PALETTE)]
            label = str(value) if str(value).strip() else "[Blank]"
            color_map[value] = st.color_picker(
                label,
                value=to_hex(default_color),
                key=safe_widget_key("color", color_col, value),
            )

    return color_map


def prepare_plot_df(df: pd.DataFrame, color_col: Optional[str], shape_col: Optional[str]) -> pd.DataFrame:
    plot_df = df.copy()
    if color_col and is_categorical(plot_df[color_col]):
        plot_df[color_col] = plot_df[color_col].fillna("[Blank]").astype(str)
    if shape_col:
        plot_df[shape_col] = plot_df[shape_col].fillna("[Blank]").astype(str)
    return plot_df


def make_hover_text(row: pd.Series, site_col: str, dimension_cols: List[str]) -> str:
    lines = [f"<b>{site_col}</b>: {row[site_col]}"]
    for col in dimension_cols:
        value = row[col]
        if pd.isna(value):
            value = "[Blank]"
        lines.append(f"<b>{col}</b>: {value}")
    return "<br>".join(lines)


def build_map_figure(
    plot_df: pd.DataFrame,
    site_col: str,
    lat_col: str,
    lon_col: str,
    dimension_cols: List[str],
    color_col: Optional[str],
    shape_col: Optional[str],
    color_map: Optional[Dict[str, str]],
    continuous_scale: Optional[str],
    zoom: int,
    height: int,
):
    center_lat = float(plot_df[lat_col].mean())
    center_lon = float(plot_df[lon_col].mean())

    fig = go.Figure()

    # Numeric high-cardinality color: one trace with a color bar. Shape is ignored here because Plotly map traces
    # cannot reliably combine continuous color bars and per-point custom marker symbols.
    if color_col and not is_categorical(plot_df[color_col]):
        fig.add_trace(
            go.Scattermap(
                lat=plot_df[lat_col],
                lon=plot_df[lon_col],
                mode="markers",
                text=[make_hover_text(row, site_col, dimension_cols) for _, row in plot_df.iterrows()],
                hoverinfo="text",
                marker={
                    "size": 12,
                    "opacity": 0.85,
                    "color": plot_df[color_col],
                    "colorscale": continuous_scale or "Viridis",
                    "showscale": True,
                    "colorbar": {"title": color_col},
                    "symbol": "circle",
                },
                name=color_col,
            )
        )
    else:
        temp = plot_df.copy()
        temp["__color_group"] = temp[color_col].fillna("[Blank]").astype(str) if color_col else "All sites"
        temp["__shape_group"] = temp[shape_col].fillna("[Blank]").astype(str) if shape_col else "All sites"

        shape_values = sorted(temp["__shape_group"].unique().tolist())
        symbol_map = {
            value: DEFAULT_SYMBOL_SEQUENCE[idx % len(DEFAULT_SYMBOL_SEQUENCE)]
            for idx, value in enumerate(shape_values)
        }

        for (color_value, shape_value), group in temp.groupby(["__color_group", "__shape_group"], dropna=False):
            marker_color = color_map.get(str(color_value), "#1f77b4") if color_map else "#1f77b4"
            trace_name = str(color_value)
            if shape_col:
                trace_name = f"{color_value} | {shape_value}" if color_col else str(shape_value)

            fig.add_trace(
                go.Scattermap(
                    lat=group[lat_col],
                    lon=group[lon_col],
                    mode="markers",
                    text=[make_hover_text(row, site_col, dimension_cols) for _, row in group.iterrows()],
                    hoverinfo="text",
                    marker={
                        "size": 12,
                        "opacity": 0.85,
                        "color": marker_color,
                        "symbol": symbol_map.get(str(shape_value), "circle"),
                    },
                    name=trace_name,
                )
            )

    fig.update_layout(
        map={
            "style": "open-street-map",
            "center": {"lat": center_lat, "lon": center_lon},
            "zoom": zoom,
        },
        height=height,
        margin={"r": 0, "t": 0, "l": 0, "b": 0},
        legend_title_text="Legend",
    )
    return fig


def main():
    st.title("Flexible Site Mapping Tool")
    st.caption("Upload a site file, choose dynamic color and shape dimensions, filter the map, and export the filtered view.")

    with st.expander("Required upload format", expanded=False):
        st.markdown(
            """
            Required columns:
            - `site code`
            - `lat`
            - `long`
            - Up to four flexible dimension columns with any field names.

            Accepted aliases include `latitude` for `lat` and `lng`, `lon`, or `longitude` for `long`.
            """
        )

    uploaded_file = st.file_uploader("Upload CSV or Excel file", type=["csv", "xlsx", "xls"])

    if uploaded_file is None:
        st.info("Upload a CSV or Excel file to begin. A sample file is included in the GitHub repo.")
        return

    try:
        if uploaded_file.name.lower().endswith(".csv"):
            raw_df = pd.read_csv(uploaded_file)
        else:
            raw_df = pd.read_excel(uploaded_file)
    except Exception as exc:
        st.error(f"Could not read the uploaded file: {exc}")
        return

    df, required_mapping, missing = clean_upload(raw_df)
    if missing:
        st.error(f"Missing required column(s): {', '.join(missing)}")
        st.stop()

    if df.empty:
        st.error("No valid rows remain after removing rows with missing or invalid latitude/longitude.")
        st.stop()

    site_col = required_mapping["site code"]
    lat_col = required_mapping["lat"]
    long_col = required_mapping["long"]
    dimension_cols = get_dimension_columns(df, required_mapping)

    if len(dimension_cols) == 0:
        st.warning("No dimension columns found. The map will still plot sites, but color and shape controls need dimension columns.")

    st.sidebar.header("Map controls")
    color_options = ["None"] + dimension_cols
    shape_options = ["None"] + dimension_cols

    color_col = st.sidebar.selectbox("Color points by", color_options, index=1 if len(color_options) > 1 else 0)
    shape_col = st.sidebar.selectbox("Shape points by", shape_options, index=0)
    color_col = None if color_col == "None" else color_col
    shape_col = None if shape_col == "None" else shape_col

    filtered_df = add_sidebar_filters(df, site_col, dimension_cols)
    if filtered_df.empty:
        st.warning("No rows match the selected filters.")
        return

    plot_df = prepare_plot_df(filtered_df, color_col, shape_col)

    color_map = None
    continuous_scale = None
    if color_col:
        if is_categorical(plot_df[color_col]):
            color_map = build_color_map(plot_df, color_col)
        else:
            continuous_scale = st.sidebar.selectbox("Continuous color scale", CONTINUOUS_COLOR_SCALES)
            if shape_col:
                st.sidebar.caption("Note: shape selection is disabled when color uses a continuous numeric scale.")

    map_height = st.sidebar.slider("Map height", min_value=450, max_value=900, value=650, step=50)
    zoom = st.sidebar.slider("Starting zoom", min_value=1, max_value=12, value=4)

    fig = build_map_figure(
        plot_df=plot_df,
        site_col=site_col,
        lat_col=lat_col,
        lon_col=long_col,
        dimension_cols=dimension_cols,
        color_col=color_col,
        shape_col=shape_col,
        color_map=color_map,
        continuous_scale=continuous_scale,
        zoom=zoom,
        height=map_height,
    )

    metric_cols = st.columns(4)
    metric_cols[0].metric("Mapped sites", f"{len(plot_df):,}")
    metric_cols[1].metric("Total uploaded rows", f"{len(df):,}")
    metric_cols[2].metric("Dimension columns", len(dimension_cols))
    metric_cols[3].metric("Filtered out", f"{len(df) - len(plot_df):,}")

    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Filtered data")
    st.dataframe(plot_df[[site_col, lat_col, long_col] + dimension_cols], use_container_width=True, hide_index=True)

    csv = plot_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download filtered data",
        data=csv,
        file_name="filtered_site_map_data.csv",
        mime="text/csv",
    )


if __name__ == "__main__":
    main()

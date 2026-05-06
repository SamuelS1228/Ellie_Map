import pandas as pd
import plotly.express as px
import streamlit as st
from typing import List, Dict

st.set_page_config(
    page_title="Flexible Site Mapping Tool",
    page_icon="🗺️",
    layout="wide",
)

REQUIRED_COLUMNS = ["site code", "lat", "long"]
MAX_DIMENSION_COLUMNS = 4
DEFAULT_SYMBOL_SEQUENCE = ["circle", "square", "diamond", "cross", "x", "triangle-up", "star"]
CONTINUOUS_COLOR_SCALES = ["Viridis", "Plasma", "Turbo", "Bluered", "RdYlGn", "Cividis", "Inferno", "Magma"]


def normalize_col_name(col: str) -> str:
    return str(col).strip().lower()


def find_required_column(df: pd.DataFrame, required_name: str) -> str | None:
    normalized_map = {normalize_col_name(c): c for c in df.columns}
    aliases = {
        "site code": ["site code", "site_code", "site", "site id", "site_id", "store", "store number"],
        "lat": ["lat", "latitude"],
        "long": ["long", "lng", "lon", "longitude"],
    }
    for alias in aliases.get(required_name, [required_name]):
        if alias in normalized_map:
            return normalized_map[alias]
    return None


def clean_upload(df: pd.DataFrame) -> tuple[pd.DataFrame, Dict[str, str], List[str]]:
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


def is_low_cardinality(series: pd.Series) -> bool:
    cleaned = series.dropna()
    if cleaned.empty:
        return True
    unique_count = cleaned.nunique()
    return unique_count <= 20 or not pd.api.types.is_numeric_dtype(cleaned)


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
        series = filtered[col]
        label = f"{col}"

        if pd.api.types.is_numeric_dtype(series) and series.dropna().nunique() > 10:
            min_val = float(series.min()) if not series.dropna().empty else 0.0
            max_val = float(series.max()) if not series.dropna().empty else 0.0
            if min_val == max_val:
                st.sidebar.caption(f"{label}: all visible values are {min_val:g}")
                continue
            selected_range = st.sidebar.slider(
                label,
                min_value=min_val,
                max_value=max_val,
                value=(min_val, max_val),
            )
            filtered = filtered[(filtered[col] >= selected_range[0]) & (filtered[col] <= selected_range[1])]
        else:
            values = sorted(series.fillna("[Blank]").astype(str).unique().tolist())
            selected_values = st.sidebar.multiselect(
                label,
                options=values,
                default=values,
            )
            compare_series = filtered[col].fillna("[Blank]").astype(str)
            filtered = filtered[compare_series.isin(selected_values)]

    return filtered


def build_color_map(df: pd.DataFrame, color_col: str) -> Dict[str, str]:
    values = sorted(df[color_col].fillna("[Blank]").astype(str).unique().tolist())
    default_palette = px.colors.qualitative.Set2 + px.colors.qualitative.Plotly + px.colors.qualitative.Safe
    color_map = {}

    with st.sidebar.expander("Choose category colors", expanded=True):
        for idx, value in enumerate(values):
            default_color = default_palette[idx % len(default_palette)]
            color_map[value] = st.color_picker(str(value), value=default_color, key=f"color_{color_col}_{value}")

    return color_map


def prepare_plot_df(df: pd.DataFrame, color_col: str | None, shape_col: str | None) -> pd.DataFrame:
    plot_df = df.copy()
    if color_col:
        plot_df[color_col] = plot_df[color_col].fillna("[Blank]").astype(str) if is_low_cardinality(plot_df[color_col]) else plot_df[color_col]
    if shape_col:
        plot_df[shape_col] = plot_df[shape_col].fillna("[Blank]").astype(str)
    return plot_df


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
            - Up to four additional flexible dimension columns. These can be any field names, such as `Senior buyer`, `Role Spend`, `Yes or No`, `Supplier`, `Region`, or `Risk Tier`.

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

    color_discrete_map = None
    color_continuous_scale = None
    if color_col:
        if is_low_cardinality(plot_df[color_col]):
            color_discrete_map = build_color_map(plot_df, color_col)
        else:
            color_continuous_scale = st.sidebar.selectbox("Continuous color scale", CONTINUOUS_COLOR_SCALES)

    map_height = st.sidebar.slider("Map height", min_value=450, max_value=900, value=650, step=50)
    zoom = st.sidebar.slider("Starting zoom", min_value=1, max_value=12, value=4)

    hover_cols = [site_col] + dimension_cols
    center_lat = plot_df[lat_col].mean()
    center_lon = plot_df[long_col].mean()

    fig = px.scatter_mapbox(
        plot_df,
        lat=lat_col,
        lon=long_col,
        color=color_col,
        symbol=shape_col,
        symbol_sequence=DEFAULT_SYMBOL_SEQUENCE,
        color_discrete_map=color_discrete_map,
        color_continuous_scale=color_continuous_scale,
        hover_name=site_col,
        hover_data={col: True for col in hover_cols if col in plot_df.columns},
        zoom=zoom,
        center={"lat": center_lat, "lon": center_lon},
        height=map_height,
    )
    fig.update_layout(
        mapbox_style="open-street-map",
        margin={"r": 0, "t": 0, "l": 0, "b": 0},
        legend_title_text="Legend",
    )
    fig.update_traces(marker={"size": 12, "opacity": 0.85})

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

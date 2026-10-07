"""
Chicago Crimes - interactive single-page Streamlit dashboard
============================================================
SETUP (once)
    pip install "streamlit>=1.50" plotly pandas numpy matplotlib openpyxl
    python crime_analysis.py Crime_Dataset.xlsx        # makes analysis_output/crimes_clean.csv.gz

RUN
    streamlit run app.py
    (optional) streamlit run app.py -- --data path/to/crimes_clean.csv.gz

Keep crime_analysis.py in the same folder: this app reuses its cleaning
and calculation functions, so numbers always match the analysis script.
"""
import os
import sys

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import crime_analysis as ca

st.set_page_config(page_title="Chicago Crimes Dashboard", page_icon="🚓", layout="wide")

BLUE, ORANGE, GREEN, RED, GREY = "#1F4E79", "#E07B39", "#4C9F70", "#C0392B", "#A6A6A6"
CAT_COL = {"Violent": RED, "Property": BLUE, "Other": GREY}
H = 330  # chart height


# --------------------------------------------------------------------------
# Data
# --------------------------------------------------------------------------
def find_data():
    args = sys.argv[1:]
    if "--data" in args:
        return args[args.index("--data") + 1]
    for p in ("analysis_output/crimes_clean.csv.gz", "crimes_clean.csv.gz"):
        if os.path.exists(p):
            return p
    return None


@st.cache_data(show_spinner="Loading data (first time only)...")
def load_data(path):
    df = pd.read_csv(path, low_memory=False, parse_dates=["Date"],
                     usecols=["ID", "Date", "Primary Type", "Arrest", "Domestic", "District", "Year"])
    df = ca.prepare(df)
    for c in ("Primary Type", "Season", "Crime Category"):
        df[c] = df[c].astype("category")
    return df.drop(columns=["ID"])


@st.cache_data(show_spinner="Updating...")
def get_results(path, types, districts, cats, years, arrest, domestic):
    df = load_data(path)
    m = df["Year"].between(years[0], years[1])
    if types:
        m &= df["Primary Type"].isin(types)
    if districts:
        m &= df["District"].isin(districts)
    if cats:
        m &= df["Crime Category"].isin(cats)
    if arrest != "All":
        m &= df["Arrest"] == (arrest == "Arrest made")
    if domestic != "All":
        m &= df["Domestic"] == (domestic == "Domestic")
    sub = df[m]
    if sub.empty:
        return None, None
    return ca.compute(sub)


# --------------------------------------------------------------------------
# Chart helpers (Plotly)
# --------------------------------------------------------------------------
def base(fig, title, xt=None, yt=None, h=H):
    fig.update_layout(title=dict(text=f"<b>{title}</b>", x=0, font=dict(size=14)),
                      height=h, margin=dict(l=10, r=10, t=45, b=10),
                      xaxis_title=xt, yaxis_title=yt, plot_bgcolor="white",
                      paper_bgcolor="white", showlegend=False, font=dict(size=11))
    fig.update_yaxes(gridcolor="#EEE")
    return fig


def col_chart(s, title, xt, yt, color=BLUE, pct=False):
    fmt = ".1f" if pct else ",.0f"
    fig = go.Figure(go.Bar(x=s.index.astype(str), y=s.values, marker_color=color,
                           text=s.values, texttemplate="%{text:" + fmt + "}",
                           textposition="outside", cliponaxis=False))
    if pct:
        fig.update_yaxes(ticksuffix="%")
    return base(fig, title, xt, yt)


def hbar(s, title, xt, color=BLUE):
    s = s.sort_values(ascending=True)  # largest on top
    fig = go.Figure(go.Bar(x=s.values, y=[str(i).title() for i in s.index], orientation="h",
                           marker_color=color, text=s.values, texttemplate="%{text:,.0f}",
                           textposition="outside", cliponaxis=False))
    fig.update_xaxes(gridcolor="#EEE")
    return base(fig, title, xt, None)


def donut(s, title, colors=None):
    fig = go.Figure(go.Pie(labels=list(s.index), values=s.values, hole=0.55,
                           marker=dict(colors=colors), sort=False, textinfo="label+percent"))
    fig.update_layout(title=dict(text=f"<b>{title}</b>", x=0, font=dict(size=14)),
                      height=H, margin=dict(l=10, r=10, t=45, b=10), showlegend=False,
                      paper_bgcolor="white")
    return fig


# --------------------------------------------------------------------------
# Page
# --------------------------------------------------------------------------
st.markdown("""
<style>
 .block-container {padding-top: 1.2rem; padding-bottom: 1rem;}
 [data-testid="stMetric"] {background:#fff; border:1px solid #D0D5DB; border-radius:8px; padding:8px 12px;}
 [data-testid="stMetricValue"] {color:#1F4E79; font-size:1.7rem;}
 [data-testid="stMetricLabel"] p {font-size:0.8rem; color:#7F7F7F;}
</style>""", unsafe_allow_html=True)

st.markdown("<h1 style='text-align:center;color:#1F4E79;margin:0'>Chicago Crimes Dashboard</h1>",
            unsafe_allow_html=True)

path = find_data()
if path is None:
    st.error("Cleaned data file not found. Run `python crime_analysis.py Crime_Dataset.xlsx` first "
             "(creates analysis_output/crimes_clean.csv.gz), or start the app with "
             "`streamlit run app.py -- --data <file>`.")
    st.stop()

full = load_data(path)

# ---- Filters (sidebar) ----
with st.sidebar:
    st.header("Filters")
    types = st.multiselect("Primary Type", sorted(full["Primary Type"].cat.categories),
                           placeholder="All crime types")
    districts = st.multiselect("District", sorted(full["District"].dropna().unique().tolist()),
                               placeholder="All districts")
    cats = st.multiselect("Crime Category", ["Violent", "Property", "Other"],
                          placeholder="All categories")
    ymin, ymax = int(full["Year"].min()), int(full["Year"].max())
    years = st.slider("Year", ymin, ymax, (ymin, ymax))
    arrest = st.radio("Arrest", ["All", "Arrest made", "No arrest"], horizontal=True)
    domestic = st.radio("Domestic", ["All", "Domestic", "Not domestic"], horizontal=True)
    st.caption("Filters apply to every KPI and chart. Fixed-period items (K5 = 2016, "
               "Q1 and K6 = Apr 2015-Jul 2017, Q4 = 2016) stay inside their period "
               "and combine with the Year slider.")

k, t = get_results(path, tuple(types), tuple(districts), tuple(cats), years, arrest, domestic)
if k is None:
    st.warning("No crimes match these filters. Widen the selection.")
    st.stop()

n = k["K1 Total crimes"]
st.caption(f"Showing {n:,} of {len(full):,} crimes")

# ---- KPI row ----
cards = [("Total crimes", f"{n:,}"),
         ("Arrest rate", f"{k['K2 Arrest rate %']:.1f}%"),
         ("Domestic crimes", f"{k['K3 Domestic crime %']:.1f}%"),
         ("Crime types", f"{k['K4 Different crime types']}"),
         ("Crimes in 2016", f"{k['K5 Crimes in 2016']:,}"),
         ("Avg / month (Apr 15-Jul 17)", f"{k['K6 Avg crimes/month (Apr15-Jul17)']:,.0f}"),
         ("Night-time crimes", f"{k['K7 Night-time crime %']:.1f}%"),
         ("Violent crimes", f"{k['K8 Violent crime %']:.1f}%")]
for c, (lab, val) in zip(st.columns(8), cards):
    c.metric(lab, val)

# ---- Row 1: Q1 (wide), Q2, Q3 ----
c1, c2, c3 = st.columns([2, 1, 1])
q1 = t["Q1 Monthly"]
with c1:
    if q1.empty:
        st.info("Q1: no data in Apr 2015 - Jul 2017 for this selection.")
    else:
        fig = go.Figure(go.Scatter(x=q1.index, y=q1.values, mode="lines+markers",
                                   line=dict(color=BLUE, width=2.5), marker=dict(size=6)))
        fig.add_trace(go.Scatter(x=[q1.idxmax(), q1.idxmin()], y=[q1.max(), q1.min()],
                                 mode="markers", marker=dict(color=ORANGE, size=11)))
        fig.update_xaxes(tickformat="%b %y", dtick="M3")
        st.plotly_chart(base(fig, "Q1 Monthly Crime Count (Apr 2015 - Jul 2017)",
                             "Month", "Number of crimes"), width="stretch")
with c2:
    st.plotly_chart(col_chart(t["Q2 Weekday"], "Q2 Crimes by Day of Week", "Day", "Crimes"),
                    width="stretch")
with c3:
    st.plotly_chart(col_chart(t["Q3 TimeOfDay"], "Q3 Crimes by Time of Day", "Time of day", "Crimes"),
                    width="stretch")

# ---- Row 2: Q4, Q5, Q6, Q7 ----
c4, c5, c6, c7 = st.columns(4)
with c4:
    st.plotly_chart(col_chart(t["Q4 Season2016"].fillna(0), "Q4 Crimes by Season (2016)",
                              "Season", "Crimes"), width="stretch")
with c5:
    s5 = t["Q5 Category"]["Crimes"].reindex(["Violent", "Property", "Other"]).fillna(0)
    st.plotly_chart(donut(s5, "Q5 Crime Category Share", [CAT_COL[i] for i in s5.index]),
                    width="stretch")
with c6:
    st.plotly_chart(col_chart(t["Q6 ArrestByTOD"].fillna(0), "Q6 Arrest Rate % by Time of Day",
                              "Time of day", "Arrest rate %", GREEN, pct=True),
                    width="stretch")
with c7:
    st.plotly_chart(hbar(t["Q7 Top10Types"], "Q7 Top 10 Crime Types", "Crimes"),
                    width="stretch")

# ---- Row 3: Q8, Q9 (wide), Q10 ----
c8, c9, c10 = st.columns([1, 2, 1])
with c8:
    st.plotly_chart(hbar(t["Q8 Top5Domestic"], "Q8 Top 5 Domestic Crime Types",
                         "Domestic crimes", RED), width="stretch")
with c9:
    q9 = t["Q9 Top10Districts"]
    xs = q9.index.astype(str)
    fig = go.Figure(go.Bar(x=xs, y=q9["Crimes"], marker_color=BLUE, name="Crimes"))
    fig.add_trace(go.Scatter(x=xs, y=q9["Arrest rate %"], mode="lines+markers", name="Arrest rate %",
                             yaxis="y2", line=dict(color=ORANGE, width=3), marker=dict(size=8)))
    fig.update_layout(yaxis2=dict(title="Arrest rate %", overlaying="y", side="right",
                                  ticksuffix="%", rangemode="tozero", showgrid=False),
                      xaxis=dict(type="category", categoryorder="array", categoryarray=list(xs)))
    base(fig, "Q9 Top 10 Districts: Crimes and Arrest Rate", "Police district", "Number of crimes")
    fig.update_layout(showlegend=True, legend=dict(orientation="h", y=1.12, x=1, xanchor="right"))
    st.plotly_chart(fig, width="stretch")
with c10:
    m = t["Q10 Heatmap"]
    fig = go.Figure(go.Heatmap(z=m.values, x=list(m.columns), y=[str(i) for i in m.index],
                               colorscale="YlOrRd", text=m.values, texttemplate="%{text:,}",
                               showscale=False, textfont=dict(size=10)))
    fig.update_yaxes(autorange="reversed")  # Monday at the top
    st.plotly_chart(base(fig, "Q10 Crimes by Day and Time of Day"), width="stretch")

# ---- Assumptions + download ----
with st.expander("Assumptions and notes"):
    st.markdown(
        "- Dates repaired for the Excel day/month swap (see `crime_analysis.py`).\n"
        "- Seasons are assigned by month only, so Dec 2016 counts as Winter 2016.\n"
        "- Average per month = rows in Apr 2015-Jul 2017 divided by 28 months.\n"
        "- Time of Day uses the hour of Date: Night 00-05, Morning 06-11, Afternoon 12-17, Evening 18-23.\n"
        "- Violent / Property / Other follow the handout's Primary Type lists.\n"
        "- Top-10 districts are ranked by crime count, not arrest rate.")
with st.expander("Download tables behind the charts"):
    for name, tbl in t.items():
        tbl = tbl.to_frame() if isinstance(tbl, pd.Series) else tbl
        st.download_button(f"{name}.csv", tbl.to_csv().encode(), f"{name.replace(' ', '_')}.csv",
                           key=name)

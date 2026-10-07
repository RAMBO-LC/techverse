"""
Chicago Crime Explorer - single-page Streamlit dashboard
=========================================================
SETUP (once)
    pip install -r requirements.txt
    (the cleaned data file analysis_output/crimes_clean.csv.gz is included;
     to rebuild it: python crime_analysis.py Crime_Dataset.xlsx)

RUN
    streamlit run app.py
    streamlit run app.py -- --data path/to/crimes_clean.csv.gz

Keep crime_analysis.py next to this file: the app reuses its cleaning and
calculation functions, so the numbers always match the analysis script.
The .streamlit/config.toml file sets the colour theme.
"""
import os
import sys

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import crime_analysis as ca

st.set_page_config(page_title="Chicago Crime Explorer", page_icon="📊", layout="wide")

# ------------------------------------------------------------------ palette
NAVY, BLUE, SKY = "#0F2A47", "#2F6FDE", "#B8CCEB"
TEAL, TEAL_L = "#14B8A6", "#B6E3DC"
AMBER, RED, RED_L, GREY = "#F59E0B", "#EF4444", "#F5B5B5", "#64748B"
CAT_COL = {"Violent": RED, "Property": BLUE, "Other": GREY}
H = 310


# ------------------------------------------------------------------ data
def find_data():
    args = sys.argv[1:]
    if "--data" in args:
        return args[args.index("--data") + 1]
    for p in ("analysis_output/crimes_clean.csv.gz", "crimes_clean.csv.gz"):
        if os.path.exists(p):
            return p
    return None


@st.cache_data(show_spinner="Loading 1M crime records (first time only)...")
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


# ------------------------------------------------------------------ charts
def style(fig, title, xt=None, yt=None, h=H):
    fig.update_layout(
        title=dict(text=f"<b>{title}</b>", x=0, font=dict(size=14, color=NAVY)),
        height=h, margin=dict(l=8, r=8, t=44, b=8), xaxis_title=xt, yaxis_title=yt,
        plot_bgcolor="#FFFFFF", paper_bgcolor="#FFFFFF", showlegend=False,
        font=dict(size=11, color="#334155"), hoverlabel=dict(bgcolor=NAVY, font_color="white"))
    fig.update_yaxes(gridcolor="#E8EDF5", zeroline=False)
    fig.update_xaxes(showgrid=False)
    return fig


def col_chart(s, title, xt, yt, accent=BLUE, muted=SKY, pct=False):
    s = s.fillna(0)
    mx = s.max()
    colors = [accent if (v == mx and mx > 0) else muted for v in s.values]
    fig = go.Figure(go.Bar(x=s.index.astype(str), y=s.values, marker_color=colors,
                           text=s.values, texttemplate="%{text:" + (".1f" if pct else ",.0f") + "}",
                           textposition="outside", cliponaxis=False, textfont=dict(color="#0F2A47", size=11),
                           hovertemplate="%{x}: %{y:,.1f}<extra></extra>" if pct else "%{x}: %{y:,.0f}<extra></extra>"))
    if pct:
        fig.update_yaxes(ticksuffix="%")
    fig.update_yaxes(range=[0, mx * 1.18 if mx > 0 else 1])
    return style(fig, title, xt, yt)


def hbar(s, title, xt, accent=BLUE, muted=SKY):
    s = s.sort_values(ascending=True)  # largest bar ends up on top
    colors = [muted] * (len(s) - 1) + [accent]
    fig = go.Figure(go.Bar(x=s.values, y=[str(i).title() for i in s.index], orientation="h",
                           marker_color=colors, text=s.values, texttemplate="%{text:,.0f}",
                           textposition="outside", cliponaxis=False, textfont=dict(color="#0F2A47", size=11),
                           hovertemplate="%{y}: %{x:,.0f}<extra></extra>"))
    fig.update_xaxes(gridcolor="#E8EDF5", range=[0, (s.max() if len(s) else 1) * 1.4])
    fig.update_yaxes(gridcolor="rgba(0,0,0,0)")
    return style(fig, title, xt, None)


def donut(s, title, colors):
    fig = go.Figure(go.Pie(labels=list(s.index), values=s.values, hole=0.62, sort=False,
                           marker=dict(colors=colors, line=dict(color="white", width=2)),
                           textinfo="label+percent", textfont=dict(color="white", size=12),
                           hovertemplate="%{label}: %{value:,.0f}<extra></extra>"))
    fig.add_annotation(text=f"<b>{s.sum():,.0f}</b><br><span style='font-size:10px'>crimes</span>",
                       showarrow=False, font=dict(size=15, color=NAVY))
    return style(fig, title)


def month_label(ts):
    return f"{ts:%b %Y}"


# ------------------------------------------------------------------ insight captions
def captions(t, n):
    c = {}
    q1 = t["Q1 Monthly"]
    c["q1"] = (f"Peak {month_label(q1.idxmax())} ({q1.max():,}) · low {month_label(q1.idxmin())} ({q1.min():,})"
               if len(q1) else "No data in Apr 2015 - Jul 2017 for this selection.")
    q2 = t["Q2 Weekday"]
    c["q2"] = f"{q2.idxmax()} is busiest ({q2.max():,})" if q2.sum() else "No data."
    q3 = t["Q3 TimeOfDay"]
    c["q3"] = f"{q3.idxmax()} holds {q3.max()/q3.sum()*100:.1f}% of crimes" if q3.sum() else "No data."
    q4 = t["Q4 Season2016"].fillna(0)
    c["q4"] = f"{q4.idxmax()} is highest in 2016 ({q4.max():,.0f})" if q4.sum() else "No 2016 data in this selection."
    q5 = t["Q5 Category"]["Share %"]
    c["q5"] = f"{q5.idxmax()} is the largest group ({q5.max():.1f}%)"
    q6 = t["Q6 ArrestByTOD"]
    c["q6"] = (f"Highest at {q6.idxmax()} ({q6.max():.1f}%), lowest at {q6.idxmin()} ({q6.min():.1f}%)"
               if q6.notna().any() else "No data.")
    q7 = t["Q7 Top10Types"]
    c["q7"] = (f"{q7.index[0].title()} leads; top 3 = {q7.iloc[:3].sum()/n*100:.0f}% of crimes"
               if len(q7) else "No data.")
    q8 = t["Q8 Top5Domestic"]
    c["q8"] = (f"{q8.index[0].title()} leads domestic crime ({q8.iloc[0]:,})"
               if len(q8) else "No domestic crimes in this selection.")
    q9 = t["Q9 Top10Districts"]
    c["q9"] = (f"District {q9.index[0]} is busiest; best arrest rate: district "
               f"{q9['Arrest rate %'].idxmax()} ({q9['Arrest rate %'].max():.1f}%)"
               if len(q9) else "No data.")
    q10 = t["Q10 Heatmap"]
    if q10.values.sum():
        d, tod = q10.stack().idxmax()
        c["q10"] = f"Busiest slot: {d} {tod} ({q10.loc[d, tod]:,})"
    else:
        c["q10"] = "No data."
    return c


# ------------------------------------------------------------------ page chrome
CSS = """
<style>
.block-container {padding-top: 1rem; padding-bottom: 2rem; max-width: 1500px;}
header[data-testid="stHeader"] {background: transparent;}
[data-testid="stVerticalBlockBorderWrapper"] {background:#fff; border:1px solid #E3EAF4 !important;
   border-radius:14px !important; box-shadow:0 2px 8px rgba(15,42,71,.06);}
.hero {background:linear-gradient(120deg,#0F2A47 0%,#1E4E8C 60%,#2F6FDE 100%); color:#fff; border-radius:16px;
   padding:22px 28px; display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;}
.hero-title {font-size:2rem; font-weight:800; letter-spacing:.2px;}
.hero-sub {opacity:.85; font-size:.95rem; margin-top:2px;}
.hero-pill {background:rgba(255,255,255,.16); border:1px solid rgba(255,255,255,.3); padding:8px 16px;
   border-radius:999px; font-weight:600; white-space:nowrap;}
.tip {background:#EAF2FF; color:#0F2A47; border-radius:10px; padding:8px 14px; font-size:.9rem; margin-bottom:12px;}
.kpi {background:#fff; border:1px solid #E3EAF4; border-top:4px solid var(--accent); border-radius:12px;
   padding:10px 12px; box-shadow:0 2px 8px rgba(15,42,71,.06); height:108px; overflow:hidden;}
.kpi-lab {font-size:.74rem; color:#334155; font-weight:600; text-transform:uppercase; letter-spacing:.4px;}
.kpi-val {font-size:1.5rem; font-weight:800; color:#0F2A47; line-height:1.2; margin-top:4px; white-space:nowrap;}
.kpi-sub {font-size:.74rem; color:#475569; margin-top:2px;}
.cap {font-size:.8rem; color:#1E293B; background:#EAF2FF; border-radius:8px; padding:5px 10px; margin-top:-4px; min-height:42px;}
.sec-title {font-size:1.3rem; font-weight:800; color:#0F2A47;}
.sec-sub {font-size:.85rem; color:#475569; margin-bottom:8px;}
</style>
"""


def kpi_html(icon, label, value, sub, color):
    return (f"<div class='kpi' style='--accent:{color}'><div class='kpi-lab'>{icon} {label}</div>"
            f"<div class='kpi-val'>{value}</div><div class='kpi-sub'>{sub}</div></div>")


# ================================================================== PAGE
S = st.session_state
st.markdown(CSS, unsafe_allow_html=True)

path = find_data()
if path is None:
    st.error("Cleaned data file not found. Run `python crime_analysis.py Crime_Dataset.xlsx` first "
             "(creates analysis_output/crimes_clean.csv.gz), or start the app with "
             "`streamlit run app.py -- --data <file>`.")
    st.stop()

full = load_data(path)
ymin, ymax = int(full["Year"].min()), int(full["Year"].max())
total = len(full)

# ---- baseline (unfiltered) results: reference for the "All data:" subtitles
kb, _ = get_results(path, (), (), (), (ymin, ymax), "All", "All")

# ---- sidebar filters
with st.sidebar:
    st.markdown("### 🎛️ Filters")

S.setdefault("f_years", (ymin, ymax))


def reset_filters():
    S.f_types, S.f_districts, S.f_cats = [], [], []
    S.f_years, S.f_arrest, S.f_domestic = (ymin, ymax), "All", "All"


with st.sidebar:
    types = st.multiselect("Primary Type", sorted(full["Primary Type"].cat.categories),
                           placeholder="All crime types", key="f_types")
    districts = st.multiselect("District", sorted(full["District"].dropna().unique().tolist()),
                               placeholder="All districts", key="f_districts")
    cats = st.multiselect("Crime Category", ["Violent", "Property", "Other"],
                          placeholder="All categories", key="f_cats")
    years = st.slider("Year", ymin, ymax, key="f_years")
    arrest = st.radio("Arrest", ["All", "Arrest made", "No arrest"], horizontal=True, key="f_arrest")
    domestic = st.radio("Domestic", ["All", "Domestic", "Not domestic"], horizontal=True, key="f_domestic")
    st.button("↺ Reset filters", on_click=reset_filters, width="stretch")
    st.caption("Filters apply to every KPI and chart. Fixed-period items (K5 = 2016, Q1 and K6 = "
               "Apr 2015-Jul 2017, Q4 = 2016) stay inside their period and combine with the Year slider.")

# ---- results for the current selection
k, t = get_results(path, tuple(types), tuple(districts), tuple(cats), years, arrest, domestic)

# ---- hero
n = total if k is None else k["K1 Total crimes"]
st.markdown(
    f"<div class='hero'><div><div class='hero-title'>📊 Chicago Crime Explorer</div>"
    f"<div class='hero-sub'>{total:,} recorded crimes · {full['Primary Type'].nunique()} crime types · "
    f"{ymin}-{ymax}</div></div>"
    f"<div class='hero-pill'>Showing {n:,} of {total:,} crimes</div></div>"
    "<div class='tip'>Use the filters in the sidebar to explore the data. "
    "Every KPI and chart updates together.</div>", unsafe_allow_html=True)

if k is None:
    st.warning("No crimes match these filters. Widen the selection or press Reset filters.")
else:
    filtered = n != total
    cap = captions(t, n)

    # ---- KPI row
    def sub(key, fmt, base_text):
        return f"All data: {fmt(kb[key])}" if filtered else base_text

    pct1 = lambda v: f"{v:.1f}%"
    num0 = lambda v: f"{v:,.0f}"
    cards = [
        ("🧾", "Total crimes", f"{n:,}", f"{n/total*100:.1f}% of all crimes" if filtered else "recorded crimes", NAVY),
        ("🚔", "Arrest rate", pct1(k["K2 Arrest rate %"]), sub("K2 Arrest rate %", pct1, "arrests ÷ crimes"), TEAL),
        ("🏠", "Domestic", pct1(k["K3 Domestic crime %"]), sub("K3 Domestic crime %", pct1, "domestic ÷ crimes"), AMBER),
        ("🗂️", "Crime types", f"{k['K4 Different crime types']}", sub("K4 Different crime types", num0, "distinct types"), BLUE),
        ("📅", "Crimes in 2016", f"{k['K5 Crimes in 2016']:,}", sub("K5 Crimes in 2016", num0, "year 2016"), NAVY),
        ("📈", "Avg / month", f"{k['K6 Avg crimes/month (Apr15-Jul17)']:,.0f}",
         sub("K6 Avg crimes/month (Apr15-Jul17)", num0, "Apr 2015 - Jul 2017"), TEAL),
        ("🌙", "Night-time", pct1(k["K7 Night-time crime %"]), sub("K7 Night-time crime %", pct1, "00:00 - 05:59"), BLUE),
        ("⚠️", "Violent", pct1(k["K8 Violent crime %"]), sub("K8 Violent crime %", pct1, "violent ÷ crimes"), RED),
    ]
    for col, (ic, lab, val, sb, colr) in zip(st.columns(8), cards):
        col.markdown(kpi_html(ic, lab, val, sb, colr), unsafe_allow_html=True)
    st.write("")

    # ---- row 1
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1, st.container(border=True):
        q1 = t["Q1 Monthly"]
        if q1.empty:
            st.info("Q1: no data in Apr 2015 - Jul 2017 for this selection.")
        else:
            fig = go.Figure(go.Scatter(x=q1.index, y=q1.values, mode="lines+markers",
                                       line=dict(color=BLUE, width=3), marker=dict(size=6, color=BLUE),
                                       hovertemplate="%{x|%b %Y}: %{y:,.0f}<extra></extra>"))
            fig.add_trace(go.Scatter(x=[q1.idxmax(), q1.idxmin()], y=[q1.max(), q1.min()], mode="markers+text",
                                     marker=dict(color=AMBER, size=12), textposition=["top center", "bottom center"],
                                     text=[f"{q1.max():,}", f"{q1.min():,}"], textfont=dict(color="#0F2A47", size=11),
                                     hoverinfo="skip"))
            fig.update_xaxes(tickformat="%b %y", dtick="M3")
            fig.update_yaxes(range=[q1.min() * 0.9, q1.max() * 1.07])
            st.plotly_chart(style(fig, "Q1 · Monthly Crime Count (Apr 2015 - Jul 2017)", "Month", "Number of crimes"),
                            width="stretch")
        st.markdown(f"<div class='cap'>💡 {cap['q1']}</div>", unsafe_allow_html=True)
    with c2, st.container(border=True):
        st.plotly_chart(col_chart(t["Q2 Weekday"], "Q2 · Crimes by Day of Week", "Day", "Crimes"), width="stretch")
        st.markdown(f"<div class='cap'>💡 {cap['q2']}</div>", unsafe_allow_html=True)
    with c3, st.container(border=True):
        st.plotly_chart(col_chart(t["Q3 TimeOfDay"], "Q3 · Crimes by Time of Day", "Time of day", "Crimes"),
                        width="stretch")
        st.markdown(f"<div class='cap'>💡 {cap['q3']}</div>", unsafe_allow_html=True)

    # ---- row 2
    c4, c5, c6, c7 = st.columns(4)
    with c4, st.container(border=True):
        st.plotly_chart(col_chart(t["Q4 Season2016"], "Q4 · Crimes by Season (2016)", "Season", "Crimes",
                                  accent=AMBER, muted="#FBE3B0"), width="stretch")
        st.markdown(f"<div class='cap'>💡 {cap['q4']}</div>", unsafe_allow_html=True)
    with c5, st.container(border=True):
        s5 = t["Q5 Category"]["Crimes"].reindex(["Violent", "Property", "Other"]).fillna(0)
        st.plotly_chart(donut(s5, "Q5 · Crime Category Share", [CAT_COL[i] for i in s5.index]), width="stretch")
        st.markdown(f"<div class='cap'>💡 {cap['q5']}</div>", unsafe_allow_html=True)
    with c6, st.container(border=True):
        st.plotly_chart(col_chart(t["Q6 ArrestByTOD"], "Q6 · Arrest Rate % by Time of Day", "Time of day",
                                  "Arrest rate %", accent=TEAL, muted=TEAL_L, pct=True), width="stretch")
        st.markdown(f"<div class='cap'>💡 {cap['q6']}</div>", unsafe_allow_html=True)
    with c7, st.container(border=True):
        st.plotly_chart(hbar(t["Q7 Top10Types"], "Q7 · Top 10 Crime Types", "Crimes"), width="stretch")
        st.markdown(f"<div class='cap'>💡 {cap['q7']}</div>", unsafe_allow_html=True)

    # ---- row 3
    c8, c9, c10 = st.columns([1, 2, 1])
    with c8, st.container(border=True):
        st.plotly_chart(hbar(t["Q8 Top5Domestic"], "Q8 · Top 5 Domestic Crime Types", "Domestic crimes",
                             accent=RED, muted=RED_L), width="stretch")
        st.markdown(f"<div class='cap'>💡 {cap['q8']}</div>", unsafe_allow_html=True)
    with c9, st.container(border=True):
        q9 = t["Q9 Top10Districts"]
        xs = [str(i) for i in q9.index]
        fig = go.Figure(go.Bar(x=xs, y=q9["Crimes"], marker_color=BLUE, name="Crimes",
                               hovertemplate="District %{x}: %{y:,.0f}<extra></extra>"))
        fig.add_trace(go.Scatter(x=xs, y=q9["Arrest rate %"], mode="lines+markers", name="Arrest rate %",
                                 yaxis="y2", line=dict(color=AMBER, width=3), marker=dict(size=9),
                                 hovertemplate="District %{x}: %{y:.1f}%<extra></extra>"))
        fig.update_layout(yaxis2=dict(title="Arrest rate %", overlaying="y", side="right", ticksuffix="%",
                                      rangemode="tozero", showgrid=False),
                          xaxis=dict(type="category", categoryorder="array", categoryarray=xs))
        style(fig, "Q9 · Top 10 Districts: Crimes and Arrest Rate", "Police district", "Number of crimes")
        fig.update_layout(showlegend=True, legend=dict(orientation="h", y=1.14, x=1, xanchor="right"))
        st.plotly_chart(fig, width="stretch")
        st.markdown(f"<div class='cap'>💡 {cap['q9']}</div>", unsafe_allow_html=True)
    with c10, st.container(border=True):
        m = t["Q10 Heatmap"]
        # NOTE: plotly heatmap textfont.color accepts only a single color, so the
        # colorscale stays light enough for dark-navy numbers on every cell.
        fig = go.Figure(go.Heatmap(z=m.values, x=list(m.columns), y=[str(i) for i in m.index],
                                   colorscale=["#FFF7E6", "#FED7AA", "#FDBA74", "#F97316"], showscale=False,
                                   text=m.values, texttemplate="%{text:,}",
                                   textfont=dict(size=10, color="#0F2A47"),
                                   hovertemplate="%{y} %{x}: %{z:,.0f}<extra></extra>", xgap=2, ygap=2))
        fig.update_yaxes(autorange="reversed", gridcolor="rgba(0,0,0,0)")  # Monday on top
        st.plotly_chart(style(fig, "Q10 · Day × Time of Day Heat Map"), width="stretch")
        st.markdown(f"<div class='cap'>💡 {cap['q10']}</div>", unsafe_allow_html=True)

# ---- notes + downloads
with st.expander("📝 Assumptions and notes"):
    st.markdown(
        "- Dates repaired for the Excel day/month swap (see `crime_analysis.py`).\n"
        "- Seasons are assigned by month only, so Dec 2016 counts as Winter 2016.\n"
        "- Average per month = rows in Apr 2015-Jul 2017 divided by 28 months.\n"
        "- Time of Day uses the hour of Date: Night 00-05, Morning 06-11, Afternoon 12-17, Evening 18-23.\n"
        "- Violent / Property / Other follow the handout's Primary Type lists.\n"
        "- Top-10 districts are ranked by crime count, not arrest rate.\n"
        "- Highlighted (darker) bars mark the highest value in each chart.")
if k is not None:
    with st.expander("⬇️ Download the tables behind the charts"):
        for name, tbl in t.items():
            tbl = tbl.to_frame() if isinstance(tbl, pd.Series) else tbl
            st.download_button(f"{name}.csv", tbl.to_csv().encode(), f"{name.replace(' ', '_')}.csv", key=f"dl_{name}")

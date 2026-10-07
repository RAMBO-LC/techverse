"""
Chicago Crimes Dashboard Competition - full analysis
=====================================================
Computes all 8 KPIs (K1-K8) and the data behind all 10 visuals (Q1-Q10),
draws every chart, builds a one-page dashboard image, and writes insights.

USAGE
    python crime_analysis.py Crime_Dataset.xlsx
    python crime_analysis.py Crimes_Dataset_Clean.csv  [output_folder]

NOTES
  * Reading the 150 MB .xlsx with pandas is slow (about 5-10 minutes).
    After the first run a cleaned copy (crimes_clean.csv.gz) is saved in
    the output folder and reused, so later runs take seconds.
  * DATE BUG IN THE .xlsx: Excel converted every date whose day is 12 or
    lower into a real date with MONTH and DAY SWAPPED (it read 03/01/2023
    as 3 Jan instead of 1 Mar). Dates with day > 12 stayed as text and are
    correct. This script detects that mix and swaps the affected dates back.
    (Check: after the fix the monthly range is 18,710-24,818, matching the
    handout. Without the fix it is 16,454-24,215.)
  * Requires: pandas, numpy, matplotlib, openpyxl.
"""
import os
import sys
import datetime as dt

import textwrap

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.gridspec import GridSpec
from matplotlib.ticker import FuncFormatter

# --------------------------------------------------------------------------
# Definitions taken from the handout
# --------------------------------------------------------------------------
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
TOD = ["Night", "Morning", "Afternoon", "Evening"]
SEASON = {12: "Winter", 1: "Winter", 2: "Winter",
          3: "Spring", 4: "Spring", 5: "Spring",
          6: "Summer", 7: "Summer", 8: "Summer",
          9: "Fall", 10: "Fall", 11: "Fall"}
VIOLENT = {"ASSAULT", "BATTERY", "ROBBERY", "HOMICIDE", "CRIM SEXUAL ASSAULT",
           "CRIMINAL SEXUAL ASSAULT", "KIDNAPPING"}
PROPERTY = {"THEFT", "BURGLARY", "MOTOR VEHICLE THEFT", "CRIMINAL DAMAGE", "ARSON"}
TREND_START, TREND_END = pd.Timestamp("2015-04-01"), pd.Timestamp("2017-07-01")
N_TREND_MONTHS = 28  # Apr 2015 .. Jul 2017 inclusive

COL = {"blue": "#1F4E79", "orange": "#E07B39", "grey": "#7F7F7F",
       "green": "#4C9F70", "red": "#C0392B"}
CAT_COL = {"Violent": "#C0392B", "Property": "#1F4E79", "Other": "#A6A6A6"}


# --------------------------------------------------------------------------
# 1. Loading and cleaning
# --------------------------------------------------------------------------
def fix_dates(col):
    """Return a datetime64 Series. Repairs the Excel day/month swap if present."""
    if pd.api.types.is_datetime64_any_dtype(col):
        print("Date column is already datetime - no repair needed.")
        return col

    is_native = col.map(lambda v: isinstance(v, (dt.datetime, pd.Timestamp)))
    out = pd.Series(pd.NaT, index=col.index, dtype="datetime64[ns]")

    # text dates, US format e.g. 07/29/2022 03:39:00 AM
    txt = col[~is_native].astype(str)
    parsed = pd.to_datetime(txt, format="%m/%d/%Y %I:%M:%S %p", errors="coerce")
    bad = parsed.isna()
    if bad.any():  # fall back to ISO-like text (e.g. the Clean CSV)
        parsed[bad] = pd.to_datetime(txt[bad], errors="coerce")
    out[~is_native] = parsed

    native = pd.to_datetime(col[is_native].astype("datetime64[ns]"))
    # Signature of the Excel bug: text dates in MM/DD format exist next to
    # real dates, and every real date has day <= 12.
    swap = (is_native.any() and (~is_native).any()
            and parsed.notna().mean() > 0.9
            and (parsed.dt.day > 12).all()
            and (native.dt.day <= 12).all())
    if swap:
        native = pd.to_datetime(dict(year=native.dt.year, month=native.dt.day,
                                     day=native.dt.month, hour=native.dt.hour,
                                     minute=native.dt.minute, second=native.dt.second))
        print(f"Excel day/month swap detected: repaired {len(native):,} dates.")
    else:
        print("No day/month swap detected.")
    out[is_native] = native
    return out


def prepare(df):
    """Clean types and add the helper columns required by the handout."""
    df = df.copy()
    df["Date"] = fix_dates(df["Date"])
    for c in ("Arrest", "Domestic"):
        df[c] = df[c].astype(str).str.upper().eq("TRUE")
    df["Year"] = pd.to_numeric(df["Year"], errors="coerce").astype("Int64")
    df["District"] = pd.to_numeric(df["District"], errors="coerce").astype("Int64")

    df["Month Start"] = df["Date"].dt.to_period("M").dt.to_timestamp()
    df["Weekday"] = pd.Categorical(df["Date"].dt.day_name(), categories=DAYS, ordered=True)
    df["Time of Day"] = pd.Categorical(
        pd.cut(df["Date"].dt.hour, [-1, 5, 11, 17, 23], labels=TOD),
        categories=TOD, ordered=True)
    df["Season"] = df["Date"].dt.month.map(SEASON)
    df["Crime Category"] = np.where(df["Primary Type"].isin(VIOLENT), "Violent",
                           np.where(df["Primary Type"].isin(PROPERTY), "Property", "Other"))
    return df


def load(path, out_dir):
    cache = os.path.join(out_dir, "crimes_clean.csv.gz")
    if os.path.exists(cache):
        print("Using cached", cache)
        df = pd.read_csv(cache, low_memory=False, parse_dates=["Date"])
        return prepare(df)
    print("Reading", path, "(slow for .xlsx)...")
    if path.lower().endswith((".xlsx", ".xlsm")):
        df = pd.read_excel(path, engine="openpyxl", dtype={"Date": object})
    else:
        df = pd.read_csv(path, low_memory=False)
    df = prepare(df)
    keep = ["ID", "Date", "Primary Type", "Description", "Location Description",
            "Arrest", "Domestic", "District", "Ward", "Community Area", "Year"]
    df[keep].to_csv(cache, index=False, compression="gzip")
    print("Saved cleaned cache:", cache)
    return df


# --------------------------------------------------------------------------
# 2. Calculations
# --------------------------------------------------------------------------
def compute(df):
    k = {}
    trend = df[(df["Month Start"] >= TREND_START) & (df["Month Start"] <= TREND_END)]
    k["K1 Total crimes"] = len(df)
    k["K2 Arrest rate %"] = df["Arrest"].mean() * 100
    k["K3 Domestic crime %"] = df["Domestic"].mean() * 100
    k["K4 Different crime types"] = df["Primary Type"].nunique()
    k["K5 Crimes in 2016"] = int((df["Year"] == 2016).sum())
    k["K6 Avg crimes/month (Apr15-Jul17)"] = len(trend) / N_TREND_MONTHS
    k["K7 Night-time crime %"] = (df["Time of Day"] == "Night").mean() * 100
    k["K8 Violent crime %"] = (df["Crime Category"] == "Violent").mean() * 100

    t = {}
    t["Q1 Monthly"] = trend.groupby("Month Start").size().rename("Crimes")
    t["Q2 Weekday"] = df["Weekday"].value_counts().reindex(DAYS).rename("Crimes")
    t["Q3 TimeOfDay"] = df["Time of Day"].value_counts().reindex(TOD).rename("Crimes")
    s2016 = df[df["Date"].dt.year == 2016]["Season"].value_counts()
    t["Q4 Season2016"] = s2016.reindex(["Winter", "Spring", "Summer", "Fall"]).rename("Crimes")
    cat = df["Crime Category"].value_counts()
    t["Q5 Category"] = pd.DataFrame({"Crimes": cat, "Share %": cat / cat.sum() * 100})
    t["Q6 ArrestByTOD"] = (df.groupby("Time of Day", observed=True)["Arrest"].mean()
                           .reindex(TOD) * 100).rename("Arrest rate %")
    t["Q7 Top10Types"] = df["Primary Type"].value_counts().head(10).rename("Crimes")
    t["Q8 Top5Domestic"] = df[df["Domestic"]]["Primary Type"].value_counts().head(5).rename("Domestic crimes")
    top_d = df["District"].value_counts().head(10).index
    q9 = (df[df["District"].isin(top_d)].groupby("District")
          .agg(Crimes=("Arrest", "size"), **{"Arrest rate %": ("Arrest", lambda s: s.mean() * 100)})
          .sort_values("Crimes", ascending=False))
    t["Q9 Top10Districts"] = q9
    t["Q10 Heatmap"] = pd.crosstab(df["Weekday"], df["Time of Day"]).reindex(DAYS)[TOD]
    return k, t


def make_insights(k, t, df):
    q1 = t["Q1 Monthly"]
    q2, q3, q4 = t["Q2 Weekday"], t["Q3 TimeOfDay"], t["Q4 Season2016"]
    q5, q6, q7 = t["Q5 Category"], t["Q6 ArrestByTOD"], t["Q7 Top10Types"]
    q8, q9, q10 = t["Q8 Top5Domestic"], t["Q9 Top10Districts"], t["Q10 Heatmap"]
    hot = q10.stack().idxmax()
    cold = q10.stack().idxmin()
    d_hi = q9["Arrest rate %"].idxmax()
    d_lo = q9["Arrest rate %"].idxmin()
    L = []
    L.append(f"Q1: Monthly crimes range from {q1.min():,} ({q1.idxmin():%b %Y}) to {q1.max():,} "
             f"({q1.idxmax():%b %Y}); summer peaks and a February dip repeat each year.")
    L.append(f"Q2: {q2.idxmax()} is the busiest day ({q2.max():,}) and {q2.idxmin()} the quietest "
             f"({q2.min():,}).")
    L.append(f"Q3: {q3.idxmax()} has the most crimes ({q3.max()/q3.sum()*100:.1f}%); "
             f"{q3.idxmin()} has the fewest ({q3.min()/q3.sum()*100:.1f}%).")
    L.append(f"Q4: In 2016, {q4.idxmax()} is highest ({q4.max():,}) and {q4.idxmin()} lowest ({q4.min():,}). "
             "Seasons are assigned by month only, so Dec 2016 counts as Winter 2016.")
    L.append(f"Q5: Violent {q5.loc['Violent','Share %']:.1f}%, Property {q5.loc['Property','Share %']:.1f}%, "
             f"Other {q5.loc['Other','Share %']:.1f}%.")
    L.append(f"Q6: Arrest rate is highest at {q6.idxmax()} ({q6.max():.1f}%) and lowest at "
             f"{q6.idxmin()} ({q6.min():.1f}%).")
    L.append(f"Q7: {q7.index[0]} is the top crime type ({q7.iloc[0]:,}); the top 3 "
             f"({', '.join(q7.index[:3])}) make up {q7.iloc[:3].sum()/k['K1 Total crimes']*100:.1f}% of all crimes.")
    L.append(f"Q8: Domestic crime is led by {q8.index[0]} ({q8.iloc[0]:,}); {q8.index[1]} is second "
             f"({q8.iloc[1]:,}).")
    L.append(f"Q9: District {q9.index[0]} has the most crimes ({q9['Crimes'].iloc[0]:,}). Among the top 10, "
             f"arrest rate is highest in district {d_hi} ({q9.loc[d_hi,'Arrest rate %']:.1f}%) and lowest "
             f"in district {d_lo} ({q9.loc[d_lo,'Arrest rate %']:.1f}%).")
    L.append(f"Q10: The busiest cell is {hot[0]} {hot[1]} ({q10.loc[hot]:,}); the quietest is "
             f"{cold[0]} {cold[1]} ({q10.loc[cold]:,}).")
    return L


# --------------------------------------------------------------------------
# 3. Charts
# --------------------------------------------------------------------------
thousands = FuncFormatter(lambda x, _: f"{x/1000:,.0f}k")
pct_fmt = FuncFormatter(lambda x, _: f"{x:.0f}%")


def style(ax, title, xlabel=None, ylabel=None):
    ax.set_title(title, fontsize=11, fontweight="bold", loc="left")
    if xlabel:
        ax.set_xlabel(xlabel, fontsize=8)
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=8)
    ax.tick_params(labelsize=8)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)


def draw_q1(ax, s):
    ax.plot(s.index, s.values, color=COL["blue"], marker="o", ms=3, lw=1.8)
    ax.scatter([s.idxmax(), s.idxmin()], [s.max(), s.min()], color=COL["orange"], zorder=3, s=22)
    ax.yaxis.set_major_formatter(thousands)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    style(ax, "Q1 Monthly Crime Count (Apr 2015 - Jul 2017)", "Month", "Number of crimes")


def draw_col(ax, s, title, xl, yl, color=COL["blue"], fmt=thousands, labels=True):
    bars = ax.bar(s.index.astype(str), s.values, color=color)
    ax.yaxis.set_major_formatter(fmt)
    if labels:
        for b, v in zip(bars, s.values):
            ax.text(b.get_x() + b.get_width() / 2, b.get_height(),
                    f"{v:,.0f}" if v > 100 else f"{v:.1f}", ha="center", va="bottom", fontsize=7)
    ax.tick_params(axis="x", rotation=30)
    style(ax, title, xl, yl)


def draw_donut(ax, s, title, colors=None):
    wedges, _, autot = ax.pie(s.values, labels=s.index, autopct="%1.1f%%", pctdistance=0.8,
                              startangle=90, counterclock=False, colors=colors,
                              wedgeprops=dict(width=0.4, edgecolor="white"),
                              textprops=dict(fontsize=8))
    for a in autot:
        a.set_fontsize(7)
    ax.set_title(title, fontsize=11, fontweight="bold", loc="left")


def draw_barh(ax, s, title, xl, color=COL["blue"]):
    s = s.sort_values(ascending=True)  # largest bar at the top
    labels = [textwrap.fill(str(i).title(), 16) for i in s.index]
    ax.barh(labels, s.values, color=color)
    ax.xaxis.set_major_formatter(thousands)
    for i, v in enumerate(s.values):
        ax.text(v, i, f" {v:,}", va="center", fontsize=7)
    style(ax, title, xl, None)
    ax.margins(x=0.15)


def draw_q9(ax, q9):
    x = np.arange(len(q9))
    ax.bar(x, q9["Crimes"], color=COL["blue"], label="Crimes")
    ax.set_xticks(x)
    ax.set_xticklabels(q9.index.astype(str))
    ax.yaxis.set_major_formatter(thousands)
    ax2 = ax.twinx()
    ax2.plot(x, q9["Arrest rate %"], color=COL["orange"], marker="o", lw=2, label="Arrest rate %")
    ax2.yaxis.set_major_formatter(pct_fmt)
    ax2.set_ylim(0, max(30, q9["Arrest rate %"].max() * 1.2))
    ax2.set_ylabel("Arrest rate %", fontsize=8)
    ax2.tick_params(labelsize=8)
    ax2.spines["top"].set_visible(False)
    style(ax, "Q9 Top 10 Districts: Crimes and Arrest Rate", "Police district", "Number of crimes")
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, fontsize=7, loc="upper right", frameon=False)


def draw_heat(ax, m):
    im = ax.imshow(m.values, cmap="YlOrRd", aspect="auto")
    ax.set_xticks(range(len(m.columns)))
    ax.set_xticklabels(m.columns, fontsize=8)
    ax.set_yticks(range(len(m.index)))
    ax.set_yticklabels(m.index.astype(str), fontsize=8)
    thr = m.values.max() * 0.6
    for i in range(m.shape[0]):
        for j in range(m.shape[1]):
            v = m.values[i, j]
            ax.text(j, i, f"{v:,}", ha="center", va="center", fontsize=7,
                    color="white" if v > thr else "black")
    ax.set_title("Q10 Crimes by Day and Time of Day", fontsize=11, fontweight="bold", loc="left")
    return im


def draw_all(k, t, out_dir):
    """Individual chart files + one-page dashboard."""
    figs = os.path.join(out_dir, "charts")
    os.makedirs(figs, exist_ok=True)

    def solo(name, fn, size=(7, 4)):
        fig, ax = plt.subplots(figsize=size)
        fn(ax)
        fig.tight_layout()
        fig.savefig(os.path.join(figs, name), dpi=130)
        plt.close(fig)

    def donut_cat(ax):
        s = t["Q5 Category"]["Crimes"].reindex(["Violent", "Property", "Other"])
        draw_donut(ax, s, "Q5 Share of Crime Categories", [CAT_COL[i] for i in s.index])

    def donut_season(ax):
        draw_donut(ax, t["Q4 Season2016"], "Q4 Crimes by Season (2016)")

    plots = {
        "Q1_monthly.png": lambda ax: draw_q1(ax, t["Q1 Monthly"]),
        "Q2_weekday.png": lambda ax: draw_col(ax, t["Q2 Weekday"], "Q2 Crimes by Day of Week", "Day", "Number of crimes"),
        "Q3_time_of_day.png": lambda ax: draw_col(ax, t["Q3 TimeOfDay"], "Q3 Crimes by Time of Day", "Time of day", "Number of crimes"),
        "Q4_season_2016.png": lambda ax: draw_col(ax, t["Q4 Season2016"], "Q4 Crimes by Season (2016)", "Season", "Number of crimes"),
        "Q5_category.png": donut_cat,
        "Q6_arrest_by_time.png": lambda ax: draw_col(ax, t["Q6 ArrestByTOD"], "Q6 Arrest Rate % by Time of Day", "Time of day", "Arrest rate %", COL["green"], pct_fmt),
        "Q7_top10_types.png": lambda ax: draw_barh(ax, t["Q7 Top10Types"], "Q7 Top 10 Crime Types", "Number of crimes"),
        "Q8_top5_domestic.png": lambda ax: draw_barh(ax, t["Q8 Top5Domestic"], "Q8 Top 5 Domestic Crime Types", "Domestic crimes", COL["red"]),
        "Q9_districts.png": lambda ax: draw_q9(ax, t["Q9 Top10Districts"]),
    }
    for name, fn in plots.items():
        solo(name, fn)
    fig, ax = plt.subplots(figsize=(6, 4.5))
    im = draw_heat(ax, t["Q10 Heatmap"])
    fig.colorbar(im, ax=ax, fraction=0.04)
    fig.tight_layout()
    fig.savefig(os.path.join(figs, "Q10_heatmap.png"), dpi=130)
    plt.close(fig)

    # ---------------- one-page dashboard ----------------
    fig = plt.figure(figsize=(22, 15), facecolor="#F4F6F8")
    gs = GridSpec(4, 4, figure=fig, height_ratios=[0.55, 2, 2, 2], hspace=0.55, wspace=0.35,
                  left=0.075, right=0.97, top=0.92, bottom=0.07)
    fig.suptitle("Chicago Crimes Dashboard", fontsize=24, fontweight="bold", color=COL["blue"], y=0.975)

    cards = [("Total crimes", f"{k['K1 Total crimes']:,}"),
             ("Arrest rate", f"{k['K2 Arrest rate %']:.1f}%"),
             ("Domestic crimes", f"{k['K3 Domestic crime %']:.1f}%"),
             ("Crime types", f"{k['K4 Different crime types']}"),
             ("Crimes in 2016", f"{k['K5 Crimes in 2016']:,}"),
             ("Avg / month (Apr15-Jul17)", f"{k['K6 Avg crimes/month (Apr15-Jul17)']:,.0f}"),
             ("Night-time crimes", f"{k['K7 Night-time crime %']:.1f}%"),
             ("Violent crimes", f"{k['K8 Violent crime %']:.1f}%")]
    sub = gs[0, :].subgridspec(1, 8, wspace=0.12)
    for i, (lab, val) in enumerate(cards):
        a = fig.add_subplot(sub[0, i])
        a.set_facecolor("white")
        a.set_xticks([]); a.set_yticks([])
        for s in a.spines.values():
            s.set_color("#D0D5DB")
        a.text(0.5, 0.58, val, ha="center", va="center", fontsize=19, fontweight="bold", color=COL["blue"])
        a.text(0.5, 0.17, lab, ha="center", va="center", fontsize=9, color=COL["grey"])

    def panel(spec):
        a = fig.add_subplot(spec)
        a.set_facecolor("white")
        return a

    draw_q1(panel(gs[1, 0:2]), t["Q1 Monthly"])
    draw_col(panel(gs[1, 2]), t["Q2 Weekday"], "Q2 Crimes by Day of Week", "Day", "Crimes")
    draw_col(panel(gs[1, 3]), t["Q3 TimeOfDay"], "Q3 Crimes by Time of Day", "Time of day", "Crimes")
    draw_col(panel(gs[2, 0]), t["Q4 Season2016"], "Q4 Crimes by Season (2016)", "Season", "Crimes")
    s5 = t["Q5 Category"]["Crimes"].reindex(["Violent", "Property", "Other"])
    draw_donut(panel(gs[2, 1]), s5, "Q5 Crime Category Share", [CAT_COL[i] for i in s5.index])
    draw_col(panel(gs[2, 2]), t["Q6 ArrestByTOD"], "Q6 Arrest Rate % by Time of Day", "Time of day",
             "Arrest rate %", COL["green"], pct_fmt)
    draw_barh(panel(gs[2, 3]), t["Q7 Top10Types"], "Q7 Top 10 Crime Types", "Crimes")
    draw_barh(panel(gs[3, 0]), t["Q8 Top5Domestic"], "Q8 Top 5 Domestic Crime Types", "Domestic crimes", COL["red"])
    draw_q9(panel(gs[3, 1:3]), t["Q9 Top10Districts"])
    draw_heat(panel(gs[3, 3]), t["Q10 Heatmap"])

    fig.text(0.075, 0.02,
             "Assumptions: dates repaired for the Excel day/month swap; seasons by month only (Dec 2016 = Winter 2016); "
             "monthly average = Apr 2015-Jul 2017 rows / 28 months; top-10 districts ranked by crime count; "
             "Time of Day by hour of Date. Add slicers (Primary Type, District) in Power BI.",
             fontsize=9, color=COL["grey"])
    fig.savefig(os.path.join(out_dir, "dashboard.png"), dpi=110)
    plt.close(fig)


# --------------------------------------------------------------------------
# 4. Run everything
# --------------------------------------------------------------------------
def run(df, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    k, t = compute(df)
    insights = make_insights(k, t, df)

    print("\n=== KPIs ===")
    for name, v in k.items():
        print(f"{name:38s} {v:>14,.2f}" if isinstance(v, float) else f"{name:38s} {v:>14,}")
    print("\n=== Insights ===")
    print("\n".join(insights))

    # sanity checks against the handout
    print("\n=== Checks against handout ===")
    print("K1 = 1,048,575:", k["K1 Total crimes"] == 1048575)
    print("K2 = 20.5%    :", round(k["K2 Arrest rate %"], 1) == 20.5)
    q1 = t["Q1 Monthly"]
    print("Q1 has 28 points:", len(q1) == 28,
          "| range 18.7k-24.8k:", 18700 <= q1.min() <= 18800 and 24700 <= q1.max() <= 24900)

    with pd.ExcelWriter(os.path.join(out_dir, "analysis_results.xlsx")) as xw:
        pd.Series(k, name="Value").to_frame().to_excel(xw, sheet_name="KPIs")
        for name, tbl in t.items():
            tbl.to_frame().to_excel(xw, sheet_name=name[:31]) if isinstance(tbl, pd.Series) \
                else tbl.to_excel(xw, sheet_name=name[:31])
    with open(os.path.join(out_dir, "insights.txt"), "w") as f:
        f.write("\n".join(insights))
    draw_all(k, t, out_dir)
    print("\nOutputs written to:", os.path.abspath(out_dir))
    return k, t


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else "Crime_Dataset.xlsx"
    out = sys.argv[2] if len(sys.argv) > 2 else "analysis_output"
    os.makedirs(out, exist_ok=True)
    run(load(src, out), out)

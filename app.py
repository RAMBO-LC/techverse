"""
Chicago Crime Explorer - gamified, single-page Streamlit dashboard
==================================================================
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
import random
import sys

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import crime_analysis as ca

st.set_page_config(page_title="Chicago Crime Explorer", page_icon="🕵️", layout="wide")

# ------------------------------------------------------------------ palette
NAVY, BLUE, SKY = "#0F2A47", "#2F6FDE", "#B8CCEB"
TEAL, TEAL_L = "#14B8A6", "#B6E3DC"
AMBER, RED, RED_L, GREY = "#F59E0B", "#EF4444", "#F5B5B5", "#94A3B8"
CAT_COL = {"Violent": RED, "Property": BLUE, "Other": GREY}
H = 310
LEVELS = [(0, "Rookie", "🔰"), (100, "Officer", "👮"), (250, "Detective", "🕵️"),
          (450, "Inspector", "🔎"), (700, "Chief", "🎖️"), (950, "Commissioner", "👑")]
FILTER_NAMES = ["Primary Type", "District", "Crime Category", "Year", "Arrest", "Domestic"]


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


# ------------------------------------------------------------------ game state
def init_state():
    S = st.session_state
    defaults = dict(xp=0, explored=set(), announced=set(), toasts=[], qi=0, answers={},
                    streak=0, best_streak=0, total_correct=0, awarded=set(), run=0,
                    finished=False, perfect=False, celebrated=False)
    for k, v in defaults.items():
        if k not in S:
            S[k] = v


def level_of(xp):
    idx = max(i for i, (th, _, _) in enumerate(LEVELS) if xp >= th)
    return idx


def add_xp(n, why):
    S = st.session_state
    before = level_of(S.xp)
    S.xp += n
    S.toasts.append(f"+{n} XP · {why}")
    after = level_of(S.xp)
    if after > before:
        S.toasts.append(f"🎉 LEVEL UP! You are now a {LEVELS[after][2]} {LEVELS[after][1]}")


def badge_defs(n_questions):
    S = st.session_state
    return [
        ("🕵️", "Rookie Detective", "Use your first filter", len(S.explored) >= 1),
        ("🧭", "Explorer", "Use 4 different filters", len(S.explored) >= 4),
        ("🔬", "Filter Master", "Use all 6 filters", len(S.explored) >= 6),
        ("🎯", "First Case Solved", "Answer a case correctly", S.total_correct >= 1),
        ("🔥", "Hot Streak", "3 correct answers in a row", S.best_streak >= 3),
        ("🧠", "Sharp Mind", "Solve 5 cases", S.total_correct >= 5),
        ("🏆", "Case Closed", "Finish every case", S.finished),
        ("💎", "Flawless", "Solve every case correctly", S.perfect),
    ]


# ------------------------------------------------------------------ charts
def style(fig, title, xt=None, yt=None, h=H):
    fig.update_layout(
        title=dict(text=f"<b>{title}</b>", x=0, font=dict(size=14, color=NAVY)),
        height=h, margin=dict(l=8, r=8, t=44, b=8), xaxis_title=xt, yaxis_title=yt,
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", showlegend=False,
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
                           textposition="outside", cliponaxis=False,
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
                           textposition="outside", cliponaxis=False,
                           hovertemplate="%{y}: %{x:,.0f}<extra></extra>"))
    fig.update_xaxes(gridcolor="#E8EDF5", range=[0, (s.max() if len(s) else 1) * 1.4])
    fig.update_yaxes(gridcolor="rgba(0,0,0,0)")
    return style(fig, title, xt, None)


def donut(s, title, colors):
    fig = go.Figure(go.Pie(labels=list(s.index), values=s.values, hole=0.62, sort=False,
                           marker=dict(colors=colors, line=dict(color="white", width=2)),
                           textinfo="label+percent", hovertemplate="%{label}: %{value:,.0f}<extra></extra>"))
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


# ------------------------------------------------------------------ quiz
def build_questions(tb, kb):
    """Questions use the FULL dataset (unaffected by filters)."""
    Q = []

    def add(text, options, answer, why, seed):
        opts = list(options)
        random.Random(seed).shuffle(opts)
        Q.append(dict(q=text, options=opts, answer=answer, why=why))

    days = ca.DAYS
    wk = tb["Q2 Weekday"]
    a = wk.idxmax()
    rng = random.Random(1)
    add("Which day of the week has the MOST recorded crimes?",
        [a] + rng.sample([d for d in days if d != a], 3), a,
        f"{a} wins with {wk.max():,} crimes, versus {wk.min():,} on {wk.idxmin()}.", 11)

    q6 = tb["Q6 ArrestByTOD"]
    a = q6.idxmax()
    add("At which time of day is a crime MOST likely to end in an arrest?",
        ca.TOD, a, f"{a}: {q6.max():.1f}% of crimes lead to arrest, versus {q6.min():.1f}% at {q6.idxmin()}.", 12)

    q8 = tb["Q8 Top5Domestic"]
    a = q8.index[0].title()
    add("What is the most common TYPE of domestic crime?",
        [i.title() for i in q8.index[:4]], a,
        f"{a} accounts for {q8.iloc[0]:,} domestic crimes, about {q8.iloc[0]/q8.iloc[1]:.0f}x the next type.", 13)

    q4 = tb["Q4 Season2016"]
    a = q4.idxmax()
    add("Which season of 2016 had the most crimes?", ["Winter", "Spring", "Summer", "Fall"], a,
        f"{a} 2016 had {q4.max():,} crimes; Winter had the fewest at {q4.min():,}.", 14)

    v = kb["K8 Violent crime %"]
    choices = [10, 20, 30, 45]
    best = min(choices, key=lambda x: abs(x - v))
    add("Roughly what share of ALL crimes are violent (assault, battery, robbery, ...)?",
        [f"About {x}%" for x in choices], f"About {best}%",
        f"Violent crimes make up {v:.1f}% of all recorded crimes.", 15)

    q9 = tb["Q9 Top10Districts"]
    a = q9["Arrest rate %"].idxmax()
    rng = random.Random(2)
    others = [d for d in q9.index if d != a]
    add("Among the 10 busiest districts, which has the HIGHEST arrest rate?",
        [f"District {a}"] + [f"District {d}" for d in rng.sample(others, 3)], f"District {a}",
        f"District {a} arrests in {q9['Arrest rate %'].max():.1f}% of crimes; the lowest is "
        f"district {q9['Arrest rate %'].idxmin()} at {q9['Arrest rate %'].min():.1f}%.", 16)

    m = tb["Q10 Heatmap"].stack().sort_values(ascending=False)
    top = m.index[0]
    rng = random.Random(3)
    alts = rng.sample(list(m.index[1:10]), 3)
    lab = lambda ix: f"{ix[0]} {ix[1]}"
    add("Which day and time slot is the BUSIEST for crime?", [lab(top)] + [lab(i) for i in alts], lab(top),
        f"{lab(top)} peaks at {m.iloc[0]:,} crimes; the quietest slot is {lab(m.index[-1])} ({m.iloc[-1]:,}).", 17)

    q1 = tb["Q1 Monthly"]
    a = q1.idxmin()
    rng = random.Random(4)
    alts = rng.sample([i for i in q1.nsmallest(8).index if i != a], 3)
    add("Between Apr 2015 and Jul 2017, which month had the FEWEST crimes?",
        [f"{a:%B %Y}"] + [f"{i:%B %Y}" for i in alts], f"{a:%B %Y}",
        f"{a:%B %Y} had only {q1.min():,} crimes (a short month) versus a peak of {q1.max():,} in {q1.idxmax():%B %Y}.", 18)
    return Q


def lock_answer(i, q):
    S = st.session_state
    choice = S.get(f"opt_{S.run}_{i}")
    if choice is None:
        S.toasts.append("Pick an answer first 🙂")
        return
    ok = choice == q["answer"]
    S.answers[i] = dict(choice=choice, ok=ok)
    if ok:
        S.streak += 1
        S.best_streak = max(S.best_streak, S.streak)
        if i not in S.awarded:
            S.awarded.add(i)
            S.total_correct += 1
            bonus = 25 if S.streak >= 3 else 0
            add_xp(100 + bonus, "Case solved" + (" + streak bonus" if bonus else ""))
    else:
        S.streak = 0


def next_case(n):
    S = st.session_state
    S.qi += 1
    if S.qi >= n:
        S.finished = True
        if all(a["ok"] for a in S.answers.values()) and len(S.answers) == n:
            S.perfect = True


def replay():
    S = st.session_state
    S.qi, S.answers, S.streak, S.celebrated = 0, {}, 0, False
    S.run += 1


def render_quiz(Q):
    S = st.session_state
    n = len(Q)
    with st.container(border=True):
        st.markdown("<div class='sec-title'>🕵️ Detective Challenge</div>"
                    "<div class='sec-sub'>Test your instincts, then see what the data says. "
                    "Answers use the full dataset (filters don't change them). +100 XP per case, "
                    "+25 bonus on a 3-answer streak.</div>", unsafe_allow_html=True)
        if S.qi >= n:
            score = sum(a["ok"] for a in S.answers.values())
            msg = ("Flawless! You read this city like a book." if score == n else
                   "Great detective work." if score >= n * 0.6 else "Keep exploring the filters and try again.")
            st.markdown(f"### 🏁 Case file closed: {score} / {n} correct")
            st.progress(score / n)
            st.success(msg)
            if score == n and not S.celebrated:
                S.celebrated = True
                st.balloons()
            if S.awarded and len(S.awarded) == n:
                st.caption("Replaying is practice mode: XP for each case is awarded only once.")
            st.button("🔁 Play again", on_click=replay, key="replay")
            return
        i = S.qi
        q = Q[i]
        st.progress(i / n, text=f"Case {i + 1} of {n}  ·  🔥 streak {S.streak}")
        st.markdown(f"#### {q['q']}")
        answered = i in S.answers
        st.radio("Your answer", q["options"], index=None, key=f"opt_{S.run}_{i}",
                 disabled=answered, label_visibility="collapsed")
        if not answered:
            st.button("🔒 Lock in answer", on_click=lock_answer, args=(i, q), key=f"lock_{S.run}_{i}")
        else:
            a = S.answers[i]
            (st.success if a["ok"] else st.error)(
                ("✅ Correct! " if a["ok"] else f"❌ Not quite. The answer is **{q['answer']}**. ") + q["why"])
            st.button("Next case →" if i < n - 1 else "See results 🏁", on_click=next_case, args=(n,),
                      key=f"next_{S.run}_{i}")


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
.kpi-lab {font-size:.74rem; color:#64748B; font-weight:600; text-transform:uppercase; letter-spacing:.4px;}
.kpi-val {font-size:1.5rem; font-weight:800; color:#0F2A47; line-height:1.2; margin-top:4px; white-space:nowrap;}
.kpi-sub {font-size:.74rem; color:#94A3B8; margin-top:2px;}
.cap {font-size:.8rem; color:#475569; background:#F4F7FC; border-radius:8px; padding:5px 10px; margin-top:-4px; min-height:42px;}
.sec-title {font-size:1.3rem; font-weight:800; color:#0F2A47;}
.sec-sub {font-size:.85rem; color:#64748B; margin-bottom:8px;}
.player {background:linear-gradient(135deg,#0F2A47,#2F6FDE); color:#fff; border-radius:14px; padding:14px 16px;}
.player .lvl {font-size:1.15rem; font-weight:800;}
.xpbar {background:rgba(255,255,255,.25); border-radius:999px; height:10px; margin:8px 0 4px;}
.xpfill {background:#FBBF24; height:10px; border-radius:999px;}
.badges {display:grid; grid-template-columns:repeat(4,1fr); gap:6px; margin-top:8px;}
.badge {text-align:center; font-size:1.5rem; background:#F1F5F9; border-radius:10px; padding:6px 0;}
.badge.locked {filter:grayscale(1); opacity:.35;}
</style>
"""


def kpi_html(icon, label, value, sub, color):
    return (f"<div class='kpi' style='--accent:{color}'><div class='kpi-lab'>{icon} {label}</div>"
            f"<div class='kpi-val'>{value}</div><div class='kpi-sub'>{sub}</div></div>")


def player_html(Q_n):
    S = st.session_state
    li = level_of(S.xp)
    th, name, icon = LEVELS[li]
    if li + 1 < len(LEVELS):
        nxt = LEVELS[li + 1][0]
        pct = (S.xp - th) / (nxt - th) * 100
        sub = f"{S.xp} / {nxt} XP to {LEVELS[li + 1][2]} {LEVELS[li + 1][1]}"
    else:
        pct, sub = 100, f"{S.xp} XP · max level reached"
    badges = badge_defs(Q_n)
    unlocked = sum(b[3] for b in badges)
    grid = "".join(f"<div class='badge {'' if b[3] else 'locked'}' title='{b[1]}: {b[2]}'>{b[0]}</div>"
                   for b in badges)
    return (f"<div class='player'><div class='lvl'>{icon} {name}</div>"
            f"<div class='xpbar'><div class='xpfill' style='width:{pct:.0f}%'></div></div>"
            f"<div style='font-size:.8rem;opacity:.9'>{sub}</div>"
            f"<div style='font-size:.8rem;margin-top:8px'>🏅 Badges {unlocked}/{len(badges)}</div>"
            f"<div class='badges'>{grid}</div></div>")


# ================================================================== PAGE
init_state()
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

# ---- baseline (unfiltered) results: used for deltas and the quiz
kb, tb = get_results(path, (), (), (), (ymin, ymax), "All", "All")
QUESTIONS = build_questions(tb, kb)

# ---- sidebar: player card placeholder first, filters below
with st.sidebar:
    player_slot = st.container()
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

# ---- award XP for exploring filters (once per filter)
active = {"Primary Type": bool(types), "District": bool(districts), "Crime Category": bool(cats),
          "Year": years != (ymin, ymax), "Arrest": arrest != "All", "Domestic": domestic != "All"}
for name, on in active.items():
    if on and name not in S.explored:
        S.explored.add(name)
        add_xp(20, f"Explored the {name} filter")

# ---- badge announcements
for ic, nm, _, got in badge_defs(len(QUESTIONS)):
    if got and nm not in S.announced:
        S.announced.add(nm)
        S.toasts.append(f"{ic} Badge unlocked: {nm}")

# ---- results for the current selection
k, t = get_results(path, tuple(types), tuple(districts), tuple(cats), years, arrest, domestic)

# ---- hero
n = len(full) if k is None else k["K1 Total crimes"]
st.markdown(
    f"<div class='hero'><div><div class='hero-title'>🕵️ Chicago Crime Explorer</div>"
    f"<div class='hero-sub'>{total:,} recorded crimes · {full['Primary Type'].nunique()} crime types · "
    f"{ymin}-{ymax} · explore, earn XP, solve the cases</div></div>"
    f"<div class='hero-pill'>Showing {n:,} of {total:,} crimes</div></div>"
    "<div class='tip'>🎮 Use the filters to earn XP and unlock badges, then scroll down to the "
    "<b>Detective Challenge</b>.</div>", unsafe_allow_html=True)

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
                                     text=[f"{q1.max():,}", f"{q1.min():,}"], hoverinfo="skip"))
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
        fig = go.Figure(go.Heatmap(z=m.values, x=list(m.columns), y=[str(i) for i in m.index],
                                   colorscale=["#FFF7E6", "#FDBA74", "#EF4444", "#7F1D1D"], showscale=False,
                                   text=m.values, texttemplate="%{text:,}", textfont=dict(size=10),
                                   hovertemplate="%{y} %{x}: %{z:,.0f}<extra></extra>", xgap=2, ygap=2))
        fig.update_yaxes(autorange="reversed", gridcolor="rgba(0,0,0,0)")  # Monday on top
        st.plotly_chart(style(fig, "Q10 · Day × Time of Day Heat Map"), width="stretch")
        st.markdown(f"<div class='cap'>💡 {cap['q10']}</div>", unsafe_allow_html=True)

# ---- challenge
render_quiz(QUESTIONS)

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

# ---- finally fill the player card and show queued toasts
player_slot.markdown(player_html(len(QUESTIONS)), unsafe_allow_html=True)
while S.toasts:
    st.toast(S.toasts.pop(0))
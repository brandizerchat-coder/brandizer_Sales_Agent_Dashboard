"""BRANDIZER · Sales Pipeline dashboard (Streamlit + pandas + Plotly).

Reads the three formula tabs published as CSV from Google Sheets:
  leads_all        (Leads file)  one row per unique lead
  outreach_report  (audit file)  one row per audited company + 0/1 flags
  activity         (audit file)  one row per event (audited, approved, sent, reply ...)
The links live in Streamlit Secrets ([data] section), never in this code.
Light / dark follows the viewer's theme (menu > Settings > Theme).
"""
from __future__ import annotations

import base64
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

CAIRO = ZoneInfo("Africa/Cairo")
HERE = Path(__file__).parent
CACHE_SECONDS = 300
YELLOW = "#E8A800"  # BRANDIZER yellow, readable on white and on black
GRAY = "#8C8C8C"    # second series (follow-ups)
INK = "#0A0A0A"

st.set_page_config(page_title="BRANDIZER · Sales Pipeline", page_icon="●", layout="wide")


# ---------------------------------------------------------------- data
def _secret(section: str, key: str, default: str = "") -> str:
    try:
        return str(st.secrets[section][key]).strip()
    except Exception:
        return default


def to_dt(s: pd.Series) -> pd.Series:
    """Sheet dates arrive as text ('11/18/2026 10:23:00', '2026-11-16 15:41:31') or as serial numbers."""
    s = s.astype(str).str.strip().replace({"": None, "nan": None, "None": None})
    num = pd.to_numeric(s, errors="coerce")
    from_serial = pd.to_datetime(num, unit="D", origin="1899-12-30", errors="coerce")
    from_text = pd.to_datetime(s.where(num.isna()), errors="coerce", format="mixed")
    out = from_text.fillna(from_serial)
    return out.where(out.dt.year > 2000)


@st.cache_data(ttl=CACHE_SECONDS, show_spinner="Loading the latest data…")
def load(leads_url: str, report_url: str, activity_url: str):
    read = lambda u: pd.read_csv(u, dtype=str, keep_default_na=False)
    leads, report, act = read(leads_url), read(report_url), read(activity_url)

    leads = leads[leads.get("place_id", "").astype(str).str.strip() != ""].drop_duplicates("place_id")
    report = report[report.get("place_id", "").astype(str).str.strip() != ""].drop_duplicates("place_id")
    act = act[(act.get("place_id", "").astype(str).str.strip() != "") & (act.get("event_date", "").astype(str).str.strip() != "")]

    leads["collected"] = to_dt(leads.get("collected_at", pd.Series("", index=leads.index)))
    leads.loc[leads["collected"].isna(), "collected"] = to_dt(leads.get("collected_date", pd.Series("", index=leads.index)))
    for c in ["last_activity_at", "snapshot_at"]:
        report[c] = to_dt(report.get(c, pd.Series("", index=report.index)))
    flags = [c for c in report.columns if c.startswith("is_")]
    report[flags] = report[flags].apply(pd.to_numeric, errors="coerce").fillna(0).astype(int)
    act["event_date"] = to_dt(act["event_date"])

    # Pipeline = every lead (left) + its outreach row; audited companies missing from leads_all are kept too.
    pipe = leads.merge(report.drop(columns=[c for c in ["is_new_7d", "lead_count"] if c in report.columns]),
                       on="place_id", how="outer", indicator=True)
    pipe[flags] = pipe[flags].fillna(0).astype(int)
    for c in ["company", "industry", "has_website", "service_category", "audit_status", "outreach_status"]:
        if c not in pipe.columns:
            pipe[c] = ""
        pipe[c] = pipe[c].fillna("").astype(str).str.strip()
    pipe["industry"] = pipe["industry"].replace("", "Unknown")
    pipe["service_category"] = pipe["service_category"].replace("", "Not matched yet")

    def status(r):
        if r["outreach_status"]:
            return r["outreach_status"]
        return "Awaiting audit" if r["has_website"] == "Yes" else "No website (not audited)"

    pipe["pipeline_status"] = pipe.apply(status, axis=1)
    pipe["awaiting_audit"] = ((pipe["has_website"] == "Yes") & (pipe["audit_status"].isin(["", "error"]))).astype(int)

    act = act.merge(pipe[["place_id", "company", "industry"]], on="place_id", how="left")
    act["industry"] = act["industry"].fillna("Unknown")
    act["service_category"] = act["service_category"].replace("", "Not matched yet")

    snapshot = report["snapshot_at"].max() if len(report) else pd.NaT
    loaded = datetime.now(CAIRO)
    return pipe, act, snapshot, loaded


# ---------------------------------------------------------------- look
def logo_html() -> str:
    """Official logo from assets/logo.(png|svg|webp) if present; otherwise the BRANDIZER wordmark in text."""
    for name in ["logo.png", "logo.svg", "logo.webp"]:
        p = HERE / "assets" / name
        if p.exists():
            mime = {"png": "image/png", "svg": "image/svg+xml", "webp": "image/webp"}[p.suffix[1:]]
            src = f"data:{mime};base64,{base64.b64encode(p.read_bytes()).decode()}"
            return f'<img src="{src}" alt="BRANDIZER" class="bz-logo">'
    return '<span class="bz-word">BRANDIZER</span>'


st.markdown(
    """
<style>
  .block-container {padding-top: 1.2rem; max-width: 1400px;}
  [data-testid="stHeader"] {background: transparent;}
  .bz-band {background:#0A0A0A; border-radius:12px; padding:22px 28px; display:flex; align-items:center;
            justify-content:space-between; gap:24px; border:1px solid #262626; border-bottom:4px solid #E8A800; margin-bottom:18px;}
  .bz-logo {height:34px; width:auto; display:block;}
  .bz-word {color:#fff; font-weight:800; letter-spacing:.22em; font-size:1.6rem;}
  .bz-title {color:#fff; font-size:1.15rem; font-weight:600; text-align:right; line-height:1.35;}
  .bz-title small {display:block; color:#BDBDBD; font-weight:400; font-size:.85rem;}
  .bz-title b {color:#E8A800;}
  [data-testid="stMetric"] {padding: 14px 16px;}
  [data-testid="stMetricValue"] {font-weight:700;}
  h3 {font-size:1.05rem !important; font-weight:600 !important; margin-bottom:0 !important;}
</style>
""",
    unsafe_allow_html=True,
)

leads_url = _secret("data", "leads_all")
report_url = _secret("data", "outreach_report")
activity_url = _secret("data", "activity")
if not (leads_url and report_url and activity_url):
    st.markdown(f'<div class="bz-band">{logo_html()}<div class="bz-title">Sales Pipeline</div></div>', unsafe_allow_html=True)
    st.error("The data links are missing. Add leads_all, outreach_report and activity under [data] in the app's Secrets.")
    st.stop()

try:
    pipe, act, snapshot, loaded = load(leads_url, report_url, activity_url)
except Exception as e:  # network or sheet problem: show it plainly
    st.markdown(f'<div class="bz-band">{logo_html()}<div class="bz-title">Sales Pipeline</div></div>', unsafe_allow_html=True)
    st.error(f"Could not read the sheets right now. Try again in a minute. ({type(e).__name__})")
    st.stop()

asof = snapshot if pd.notna(snapshot) else loaded
st.markdown(
    f'<div class="bz-band">{logo_html()}<div class="bz-title">Sales Pipeline'
    f'<small>Data as of <b>{asof:%d %b %Y, %H:%M}</b> · Cairo time</small></div></div>',
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------- filters (one row)
f1, f2, f3, f4 = st.columns([1.3, 1, 1, 1])
dates = pipe["collected"].dropna()
lo = dates.min().date() if len(dates) else datetime.now(CAIRO).date()
hi = max(dates.max().date() if len(dates) else lo, datetime.now(CAIRO).date())
period = f1.date_input("Period", value=(lo, hi), min_value=lo, max_value=hi, format="DD/MM/YYYY")
ind_sel = f2.multiselect("Industry", sorted(pipe["industry"].unique()), placeholder="All industries")
cat_sel = f3.multiselect("Service category", sorted(pipe["service_category"].unique()), placeholder="All categories")
sta_sel = f4.multiselect("Status", sorted(pipe["pipeline_status"].unique()), placeholder="All statuses")

d0, d1 = (period if isinstance(period, (list, tuple)) and len(period) == 2 else (lo, hi))
p = pipe.copy()
in_range = p["collected"].isna() | p["collected"].dt.date.between(d0, d1)
p = p[in_range]
if ind_sel:
    p = p[p["industry"].isin(ind_sel)]
if cat_sel:
    p = p[p["service_category"].isin(cat_sel)]
if sta_sel:
    p = p[p["pipeline_status"].isin(sta_sel)]

a = act[act["place_id"].isin(p["place_id"]) & act["event_date"].dt.date.between(d0, d1)]

# ---------------------------------------------------------------- KPIs
total = int((p["_merge"] != "right_only").sum())
week_ago = pd.Timestamp(datetime.now(CAIRO).date() - timedelta(days=6))
new7 = int((p["collected"] >= week_ago).sum())
s = lambda c: int(p[c].sum()) if c in p.columns else 0
contacted, replied = s("is_contacted"), s("is_replied")
rate = f"{replied / contacted:.0%}" if contacted else "—"


def kpi_row(items):
    for col, (label, value, help_) in zip(st.columns(len(items)), items):
        col.metric(label, value, help=help_, border=True)


kpi_row([
    ("Total leads", f"{total:,}", "Unique companies collected from Google Maps (each counted once)."),
    ("New this week", f"{new7:,}", "Leads collected in the last 7 days."),
    ("Awaiting audit", f"{s('awaiting_audit'):,}", "Companies with a website that are not audited yet."),
    ("Audited", f"{s('is_audited'):,}", "Websites checked by the audit workflow."),
    ("Qualified", f"{s('is_qualified'):,}", "Audited and good enough for a personalised email."),
    ("Pending approval", f"{s('is_pending_approval'):,}", "Emails waiting for your Approve / Reject decision."),
])
st.write("")
kpi_row([
    ("Rejected", f"{s('is_rejected'):,}", "Emails rejected at approval."),
    ("Emails sent", f"{contacted:,}", "Companies that received the first email."),
    ("Follow-ups sent", f"{s('is_followup_sent'):,}", "The single follow-up, sent after 3 working days."),
    ("Replies to confirm", f"{s('is_reply_awaiting'):,}", "Replies detected automatically, waiting for a person to mark YES or NO."),
    ("Confirmed replies", f"{replied:,}", "Replies a person marked YES."),
    ("Reply rate", rate, "Confirmed replies ÷ companies emailed."),
])


# ---------------------------------------------------------------- charts
def base_layout(fig: go.Figure, height: int = 320, legend: bool = False) -> go.Figure:
    fig.update_layout(height=height, margin=dict(l=8, r=8, t=8, b=8), bargap=0.35, showlegend=legend,
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title=None),
                      hoverlabel=dict(namelength=-1))
    # Clean look: no grid lines, no axis lines; every bar carries its own number instead.
    fig.update_xaxes(showgrid=False, zeroline=False, showline=False, ticks="")
    fig.update_yaxes(showgrid=False, zeroline=False, showline=False, ticks="", rangemode="tozero")
    return fig


def values_only(fig: go.Figure, peak: float) -> go.Figure:
    # Vertical bars: hide the value axis and leave headroom so the labels above bars never clip.
    fig.update_yaxes(visible=False, range=[0, max(peak, 1) * 1.18])
    fig.update_traces(textfont=dict(size=13))
    return fig


def show(fig):
    st.plotly_chart(fig, width="stretch", theme="streamlit", config={"displayModeBar": False})


def empty(msg: str):
    st.info(msg)


def hbar(series: pd.Series, top: int | None = None, unit: str = "leads"):
    series = series.sort_values(ascending=False)
    if top:
        series = series.head(top)
    series = series.iloc[::-1]
    fig = go.Figure(go.Bar(x=series.values, y=series.index, orientation="h", text=series.values,
                           textposition="outside", cliponaxis=False, marker=dict(color=YELLOW, cornerradius=4),
                           hovertemplate=f"%{{y}}: %{{x}} {unit}<extra></extra>"))
    fig = base_layout(fig, height=max(240, 34 * len(series) + 40))
    fig.update_traces(textfont=dict(size=13))
    fig.update_xaxes(visible=False, range=[0, max(series.max(), 1) * 1.2])
    fig.update_yaxes(title=None, automargin=True)
    return fig


def weekly(dates: pd.Series) -> pd.Series:
    # Weeks start on Sunday (Egyptian work week).
    return dates.dt.to_period("W-SAT").dt.start_time


def week_labels(idx) -> list[str]:
    return [f"Week of {d:%d %b}" for d in idx]


def slim(fig: go.Figure, n: int) -> go.Figure:
    # Keep bars slim when there are only a few weeks of data.
    if n < 5:
        fig.update_traces(width=0.12 * n + 0.18, selector=dict(type="bar"))
    return fig


c1, c2 = st.columns(2)
with c1:
    st.subheader("Pipeline funnel")
    stages = [("Leads", total), ("Audited", s("is_audited")), ("Qualified", s("is_qualified")),
              ("Approved", s("is_approved")), ("Emailed", contacted), ("Replied", replied)]
    fig = go.Figure(go.Funnel(y=[x for x, _ in stages], x=[v for _, v in stages], texttemplate="<b>%{value}</b>  ·  %{percentInitial:.0%}",
                              textposition="outside", textfont=dict(size=13),
                              marker=dict(color=YELLOW),
                              hovertemplate="%{y}: %{x}<extra></extra>",
                              connector=dict(fillcolor="rgba(140,140,140,0.15)", line=dict(width=0))))
    fig = base_layout(fig)
    fig.update_layout(margin=dict(l=8, r=90, t=8, b=8))
    fig.update_traces(cliponaxis=False)
    fig.update_xaxes(visible=False)
    fig.update_yaxes(title=None)
    show(fig)
with c2:
    st.subheader("Leads collected per week")
    w = weekly(p["collected"].dropna()).value_counts().sort_index()
    if w.empty:
        empty("No leads in this period.")
    else:
        fig = go.Figure(go.Bar(x=week_labels(w.index), y=w.values, text=w.values, textposition="outside", cliponaxis=False,
                               marker=dict(color=YELLOW, cornerradius=4), hovertemplate="%{x}: %{y} leads<extra></extra>"))
        fig = values_only(slim(base_layout(fig), len(w)), w.max())
        fig.update_xaxes(type="category", title=None)
        show(fig)

c3, c4 = st.columns(2)
with c3:
    st.subheader("Emails sent per week")
    e = a[a["event_type"].isin(["Initial email sent", "Follow-up sent"])]
    if e.empty:
        empty("No emails sent in this period yet.")
    else:
        e = e.assign(week=weekly(e["event_date"]))
        t = e.pivot_table(index="week", columns="event_type", values="place_id", aggfunc="count", fill_value=0)
        fig = go.Figure()
        for name in ["Initial email sent", "Follow-up sent"]:
            if name in t.columns:
                label = "First email" if name == "Initial email sent" else "Follow-up"
                fig.add_bar(name=label, x=week_labels(t.index), y=t[name],
                            text=[v if v else "" for v in t[name]], textposition="inside", insidetextanchor="middle",
                            textfont=dict(color=INK if name == "Initial email sent" else "#FFFFFF", size=13),
                            marker=dict(color=YELLOW if name == "Initial email sent" else GRAY, cornerradius=4,
                                        line=dict(width=0)),
                            hovertemplate=f"{label} · %{{x}}: %{{y}}<extra></extra>")
        totals = t.sum(axis=1)
        fig.add_scatter(x=week_labels(t.index), y=totals, mode="text", text=[f"<b>{v}</b>" for v in totals],
                        textposition="top center", textfont=dict(size=13), showlegend=False, hoverinfo="skip")
        fig = values_only(slim(base_layout(fig, legend=True), len(t)), totals.max())
        fig.update_layout(barmode="stack", legend_traceorder="normal")
        fig.update_xaxes(type="category", title=None)
        show(fig)
with c4:
    st.subheader("Replies per week")
    r = a[a["event_type"] == "Reply detected"]
    if r.empty:
        empty("No replies in this period yet.")
    else:
        rw = weekly(r["event_date"]).value_counts().sort_index()
        fig = go.Figure(go.Bar(x=week_labels(rw.index), y=rw.values, text=rw.values, textposition="outside", cliponaxis=False,
                               marker=dict(color=YELLOW, cornerradius=4), hovertemplate="%{x}: %{y} replies<extra></extra>"))
        fig = values_only(slim(base_layout(fig), len(rw)), rw.max())
        fig.update_xaxes(type="category", title=None)
        show(fig)

c5, c6, c7 = st.columns(3)
with c5:
    st.subheader("Top industries")
    show(hbar(p["industry"].value_counts(), top=10))
with c6:
    st.subheader("Service category")
    audited = p[p["is_audited"] == 1]
    if audited.empty:
        empty("No audited companies in this period.")
    else:
        show(hbar(audited["service_category"].value_counts(), unit="companies"))
with c7:
    st.subheader("Where leads are now")
    show(hbar(p["pipeline_status"].value_counts()))

st.subheader("Latest activity")
recent = (p[p["last_activity_at"].notna()].sort_values("last_activity_at", ascending=False).head(20)
          [["company", "industry", "service_category", "pipeline_status", "last_activity_at"]])
if recent.empty:
    empty("No activity yet.")
else:
    st.dataframe(
        recent, hide_index=True, width="stretch",
        column_config={
            "company": "Company", "industry": "Industry", "service_category": "Service category",
            "pipeline_status": "Status",
            "last_activity_at": st.column_config.DatetimeColumn("Last activity", format="DD MMM YYYY, HH:mm"),
        },
    )

st.caption(f"Updates automatically from the BRANDIZER sales workflows · refreshed {loaded:%H:%M}")

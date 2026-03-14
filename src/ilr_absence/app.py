"""
UK ILR Absence Calculator
─────────────────────────
Track UK absences and check eligibility for Indefinite Leave to Remain (ILR).

Rules implemented:
    • 180-day rolling 12-calendar-month window (all routes)
    • Total absence cap (10-year Long Residence: 548 days)
    • Single-trip duration check (no trip > 6 months)
"""

import bisect
from datetime import date, timedelta
from io import BytesIO

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from pycountry import countries
import streamlit as st
from dateutil.relativedelta import relativedelta

COUNTRIES = sorted(c.name for c in countries)

REASONS = ["Holiday", "Family Visit", "Business", "Emergency", "Medical", "Other"]

st.set_page_config(
    page_title="UK ILR Absence Calculator – Check Your Eligibility",
    page_icon="🇬🇧",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
<style>
  .main .block-container{padding-top:1.5rem}
  div[data-testid="stMetric"]{
      background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);
      padding:1rem 1.25rem;border-radius:12px;
      box-shadow:0 4px 15px rgba(102,126,234,.3)}
  div[data-testid="stMetric"] label{color:rgba(255,255,255,.85)!important}
  div[data-testid="stMetric"] [data-testid="stMetricValue"]{color:#fff!important}
  div[data-testid="stMetric"] [data-testid="stMetricDelta"]{color:rgba(255,255,255,.9)!important}
  .risk-low{background:#d4edda;border-left:5px solid #28a745;padding:1rem;border-radius:8px;margin:1rem 0}
  .risk-med{background:#fff3cd;border-left:5px solid #ffc107;padding:1rem;border-radius:8px;margin:1rem 0}
  .risk-high{background:#f8d7da;border-left:5px solid #dc3545;padding:1rem;border-radius:8px;margin:1rem 0}
  .cta-box{background:linear-gradient(135deg,#f093fb 0%,#f5576c 100%);
           padding:2rem;border-radius:16px;text-align:center;color:#fff;margin:2rem 0}
  .footer{text-align:center;color:#999;padding:2rem 0;font-size:.85rem;
          border-top:1px solid #eee;margin-top:3rem}
  #MainMenu{visibility:hidden}
  footer{visibility:hidden}
  .stTabs [data-baseweb="tab-list"]{gap:8px}
</style>
""",
    unsafe_allow_html=True,
)

ROUTES: dict[str, dict] = {
    "5-Year Route (Skilled Worker, Spouse, Innovator, etc.)": {
        "years": 5,
        "total_limit": None,
        "rolling_limit": 180,
        "single_trip_limit": 180,
        "desc": "Includes Skilled Worker, Health & Care, Spouse/Partner, Innovator Founder, and other 5-year routes.",
    },
    "10-Year Long Residence": {
        "years": 10,
        "total_limit": 548,
        "rolling_limit": 180,
        "single_trip_limit": 180,
        "desc": "Based on 10 years' continuous lawful residence in the UK.",
    },
}


# ══════════════════════════════════════════════════════════════
# Core calculation engine
# ══════════════════════════════════════════════════════════════
class ILRAbsenceEngine:
    """Analyses UK absences against Home Office continuous-residence rules."""

    def __init__(
        self,
        route_cfg: dict,
        visa_start: date,
        planned_ilr: date,
        raw_trips: list[dict],
    ):
        self.cfg = route_cfg
        self.visa_start = visa_start
        self.planned_ilr = planned_ilr
        self.trips = self._clean(raw_trips)
        self._absence_set: set[date] = self._build_absence_set()
        self._sorted_ord: list[int] = sorted(d.toordinal() for d in self._absence_set)

    # ── helpers ──────────────────────────────────────────────
    def _clean(self, raw: list[dict]) -> list[dict]:
        out = []
        for t in raw:
            dep, ret = t.get("departure"), t.get("return")
            if dep and ret and dep <= ret:
                out.append(
                    {
                        "departure": dep,
                        "return": ret,
                        "destination": t.get("destination", ""),
                        "reason": t.get("reason", ""),
                    }
                )
        return sorted(out, key=lambda x: x["departure"])

    def _build_absence_set(self) -> set[date]:
        """Both departure and return days count as absent (Home Office practice)."""
        days: set[date] = set()
        for t in self.trips:
            d = t["departure"]
            while d <= t["return"]:
                if self.visa_start <= d <= self.planned_ilr:
                    days.add(d)
                d += timedelta(days=1)
        return days

    def _count_in_range(self, start: date, end: date) -> int:
        lo = bisect.bisect_left(self._sorted_ord, start.toordinal())
        hi = bisect.bisect_right(self._sorted_ord, end.toordinal())
        return hi - lo

    # ── basic metrics ────────────────────────────────────────
    @property
    def total_absent(self) -> int:
        return len(self._absence_set)

    @property
    def qualifying_days(self) -> int:
        return (self.planned_ilr - self.visa_start).days + 1

    @property
    def days_in_uk(self) -> int:
        return self.qualifying_days - self.total_absent

    @property
    def residence_pct(self) -> float:
        return (self.days_in_uk / self.qualifying_days * 100) if self.qualifying_days else 100.0

    @property
    def earliest_ilr(self) -> date:
        return self.visa_start + relativedelta(years=self.cfg["years"])

    @property
    def earliest_application(self) -> date:
        """Can apply up to 28 days before completing qualifying period."""
        return self.earliest_ilr - timedelta(days=28)

    # ── trip details ─────────────────────────────────────────
    def trip_table(self) -> list[dict]:
        rows = []
        for t in self.trips:
            dur = (t["return"] - t["departure"]).days + 1
            risk = "🔴 High" if dur > 180 else ("🟡 Caution" if dur > 150 else "🟢 OK")
            rows.append(
                {
                    "Departure": t["departure"],
                    "Return": t["return"],
                    "Destination": t["destination"],
                    "Reason": t["reason"],
                    "Days Absent": dur,
                    "Risk": risk,
                }
            )
        return rows

    def longest_trip(self) -> tuple[int, dict | None]:
        rows = self.trip_table()
        if not rows:
            return 0, None
        best = max(rows, key=lambda r: r["Days Absent"])
        return best["Days Absent"], best

    # ── rolling 12-calendar-month window ─────────────────────
    def rolling_analysis(self) -> tuple[int, date | None, date | None, list[dict]]:
        """
        Correct Home Office method: 12 calendar months, not 365 days.
        Returns (max_days, window_start, window_end, high_risk_windows).
        """
        if not self._sorted_ord:
            return 0, None, None, []

        # Build candidate end-dates: trip boundaries ±7 days, monthly markers
        candidates: set[date] = set()
        for t in self.trips:
            for base in (t["departure"], t["return"]):
                for off in range(-7, 8):
                    d1 = base + timedelta(days=off)
                    if self.visa_start <= d1 <= self.planned_ilr:
                        candidates.add(d1)
                    d2 = base + relativedelta(months=12) + timedelta(days=off)
                    if self.visa_start <= d2 <= self.planned_ilr:
                        candidates.add(d2)
        d = self.visa_start
        while d <= self.planned_ilr:
            candidates.add(d)
            d += relativedelta(months=1)
        candidates.add(self.planned_ilr)

        max_days = 0
        w_start = w_end = None
        risky: list[dict] = []

        for end in sorted(candidates):
            start = end - relativedelta(months=12) + timedelta(days=1)
            if start < self.visa_start:
                start = self.visa_start
            cnt = self._count_in_range(start, end)
            if cnt > max_days:
                max_days, w_start, w_end = cnt, start, end
            if cnt > 150:
                risky.append({"start": start, "end": end, "days_absent": cnt})

        return max_days, w_start, w_end, risky

    # ── budget ───────────────────────────────────────────────
    def remaining_budget(self) -> dict:
        max_roll, *_ = self.rolling_analysis()
        roll_left = max(0, self.cfg["rolling_limit"] - max_roll)
        out: dict = {"rolling_remaining": roll_left}
        if self.cfg["total_limit"] is not None:
            tot_left = max(0, self.cfg["total_limit"] - self.total_absent)
            out["total_remaining"] = tot_left
            out["effective"] = min(roll_left, tot_left)
        else:
            out["effective"] = roll_left
        return out

    # ── calendar-year breakdown ──────────────────────────────
    def yearly_breakdown(self) -> list[dict]:
        if not self._absence_set:
            return []
        by_year: dict[int, int] = {}
        for d in self._absence_set:
            by_year[d.year] = by_year.get(d.year, 0) + 1
        rows = []
        for yr in sorted(by_year):
            ys = max(date(yr, 1, 1), self.visa_start)
            ye = min(date(yr, 12, 31), self.planned_ilr)
            tot = (ye - ys).days + 1
            ab = by_year[yr]
            rows.append(
                {"Year": yr, "Days Absent": ab, "Days in UK": tot - ab, "Absence %": round(ab / tot * 100, 1)}
            )
        return rows

    # ── monthly data (for charts) ────────────────────────────
    def monthly_data(self) -> pd.DataFrame:
        if not self._absence_set:
            return pd.DataFrame()
        rows = []
        cur = self.visa_start.replace(day=1)
        while cur <= self.planned_ilr:
            me = min((cur + relativedelta(months=1)) - timedelta(days=1), self.planned_ilr)
            ab = sum(1 for d in self._absence_set if cur <= d <= me)
            tot = (me - cur).days + 1
            rows.append({"Month": cur.strftime("%b %Y"), "month_dt": cur, "Days Absent": ab, "Days in UK": tot - ab})
            cur += relativedelta(months=1)
        return pd.DataFrame(rows)

    # ── eligibility verdict ──────────────────────────────────
    def assess(self) -> tuple[str, list[str], list[str]]:
        issues: list[str] = []
        warns: list[str] = []
        max_roll, ws, we, _ = self.rolling_analysis()
        lt, _ = self.longest_trip()

        # 180-day rule
        if max_roll > self.cfg["rolling_limit"]:
            issues.append(
                f"❌ **180-day breach**: {max_roll} days absent between "
                f"{ws:%d %b %Y} – {we:%d %b %Y}.  Limit is {self.cfg['rolling_limit']}."
            )
        elif max_roll > 150:
            warns.append(
                f"⚠️ **Approaching 180-day limit**: {max_roll} days in worst window.  "
                f"Only **{self.cfg['rolling_limit'] - max_roll}** days of headroom."
            )

        # Single trip
        if lt > self.cfg["single_trip_limit"]:
            issues.append(f"❌ **Single trip > 6 months**: longest trip was {lt} days (limit {self.cfg['single_trip_limit']}).")
        elif lt > 150:
            warns.append(f"⚠️ **Long trip**: {lt} days.  Limit is {self.cfg['single_trip_limit']}.")

        # Total cap (10-yr)
        if self.cfg["total_limit"] is not None:
            if self.total_absent > self.cfg["total_limit"]:
                issues.append(
                    f"❌ **Total absence cap exceeded**: {self.total_absent} days "
                    f"(cap {self.cfg['total_limit']})."
                )
            elif self.total_absent > self.cfg["total_limit"] * 0.9:
                warns.append(
                    f"⚠️ **Near total cap**: {self.total_absent} / {self.cfg['total_limit']} days used."
                )

        # Qualifying period
        today = date.today()
        if today < self.earliest_ilr:
            rem = (self.earliest_ilr - today).days
            warns.append(f"📅 **Qualifying period incomplete**: {rem} days until {self.earliest_ilr:%d %b %Y}.")

        status = "FAIL" if issues else ("CAUTION" if warns else "PASS")
        return status, issues, warns


# ═══════════════════════════════════════════════════════════════
# UI Sections
# ═══════════════════════════════════════════════════════════════

def _header():
    st.markdown(
        """
    <div style="text-align:center;padding:0.5rem 0 1.5rem">
        <h1 style="font-size:2.5rem;font-weight:700;margin-bottom:.25rem">
            🇬🇧 UK ILR Absence Calculator
        </h1>
        <p style="font-size:1.1rem;color:#666;max-width:680px;margin:.5rem auto">
            Track your absences, check the 180-day rule, and assess your Indefinite Leave to Remain
            eligibility — free and instant.
        </p>
    </div>
    """,
        unsafe_allow_html=True,
    )


def _sidebar() -> tuple[dict, date, date]:
    with st.sidebar:
        st.markdown("### ⚙️ Configuration")
        route_name = st.selectbox("ILR Route", list(ROUTES.keys()), help="Select your visa route to ILR")
        cfg = ROUTES[route_name]
        st.caption(cfg["desc"])
        st.divider()

        c1, c2 = st.columns(2)
        with c1:
            visa_start = st.date_input(
                "Visa Start Date",
                value=date.today() - relativedelta(years=cfg["years"]),
                help="Date your current qualifying visa started",
            )
        with c2:
            planned_ilr = st.date_input(
                "Planned ILR Date",
                value=visa_start + relativedelta(years=cfg["years"]),
                help="When you plan to apply for ILR",
            )

        if planned_ilr <= visa_start:
            st.error("ILR date must be after visa start date.")
            st.stop()

        st.divider()
        st.markdown("### 📋 Key Rules")
        st.markdown(
            f"""
| Rule | Limit |
|------|-------|
| Max absence / 12 months | **{cfg['rolling_limit']} days** |
| Max single trip | **{cfg['single_trip_limit']} days** |
| Total absence cap | **{cfg['total_limit'] or 'N/A (rolling only)'}** |
| Qualifying period | **{cfg['years']} years** |
"""
        )
        st.divider()
        st.info(
            "💡 The Home Office counts **both** departure and return days "
            "as days outside the UK.  Plan accordingly!"
        )
    return cfg, visa_start, planned_ilr


def _trip_editor() -> list[dict]:
    st.markdown("### ✈️  Your Trips Outside the UK")
    st.caption("Add every trip where you left the UK, including the day you departed and the day you returned.")

    if "trips" not in st.session_state:
        st.session_state.trips = []

    with st.form("add_trip", clear_on_submit=True):
        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            travel_dates = st.date_input(
                "Travel Period",
                value=(date.today(), date.today()),
                help="Pick your departure date then your return date — both count as days outside the UK.",
            )
        with col2:
            destination = st.selectbox(
                "Destination Country",
                options=COUNTRIES,
                index=None,
                placeholder="Type or select…",
                accept_new_options=True,
            )
        with col3:
            reason = st.selectbox(
                "Reason",
                options=REASONS,
                index=None,
                placeholder="Type or select…",
                accept_new_options=True,
            )
        if st.form_submit_button("➕ Add Trip", use_container_width=True):
            if isinstance(travel_dates, (list, tuple)) and len(travel_dates) == 2:
                dep, ret = travel_dates
                if dep <= ret:
                    st.session_state.trips.append({
                        "departure": dep,
                        "return": ret,
                        "destination": str(destination or ""),
                        "reason": str(reason or ""),
                    })
                else:
                    st.error("Return date must be on or after the departure date.")
            else:
                st.error("Please select both a departure and a return date.")

    if st.session_state.trips:
        st.markdown("**Trips added** — edit inline, or select rows and press Delete to remove them.")
        trips_df = pd.DataFrame([
            {
                "Departure": t["departure"],
                "Return": t["return"],
                "Destination": t["destination"],
                "Reason": t["reason"],
            }
            for t in st.session_state.trips
        ])
        edited = st.data_editor(
            trips_df,
            num_rows="dynamic",
            width="stretch",
            column_config={
                "Departure": st.column_config.DateColumn("Departure", required=True),
                "Return": st.column_config.DateColumn("Return", required=True),
                "Destination": st.column_config.TextColumn("Destination"),
                "Reason": st.column_config.TextColumn("Reason"),
            },
            key="trip_table",
        )
        # Sync edits back to session state
        st.session_state.trips = [
            {
                "departure": row["Departure"].date() if isinstance(row["Departure"], pd.Timestamp) else row["Departure"],
                "return": row["Return"].date() if isinstance(row["Return"], pd.Timestamp) else row["Return"],
                "destination": str(row.get("Destination") or ""),
                "reason": str(row.get("Reason") or ""),
            }
            for _, row in edited.iterrows()
            if pd.notna(row.get("Departure")) and pd.notna(row.get("Return"))
        ]

    return st.session_state.trips


# ── result panels ────────────────────────────────────────────


def _show_results(eng: ILRAbsenceEngine):
    st.markdown("---")
    st.markdown("## 📊  Your ILR Absence Report")

    max_roll, ws, we, risky = eng.rolling_analysis()
    budget = eng.remaining_budget()
    lt, _ = eng.longest_trip()

    # ── headline metrics
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total Days Absent", eng.total_absent)
    c2.metric("Days in UK", eng.days_in_uk)
    c3.metric(
        "Worst 12-Month Window",
        f"{max_roll} days",
        delta=f"{eng.cfg['rolling_limit'] - max_roll} remaining",
        delta_color="inverse" if max_roll > 150 else "normal",
    )
    c4.metric("Longest Single Trip", f"{lt} days")
    c5.metric("Safe Days Remaining", f"{budget['effective']} days")

    # ── eligibility banner
    status, issues, warns = eng.assess()
    st.markdown("### 🎯  Eligibility Assessment")

    banners = {
        "PASS": (
            "risk-low",
            "✅ ELIGIBLE — No Issues Detected",
            "Based on the absences entered you meet the continuous-residence requirement.",
        ),
        "CAUTION": (
            "risk-med",
            "⚠️ CAUTION — Review Warnings",
            "No outright breaches, but there are areas of concern.",
        ),
        "FAIL": (
            "risk-high",
            "❌ POTENTIAL BREACH DETECTED",
            "One or more ILR requirements may not be met.",
        ),
    }
    cls, title, body = banners[status]
    st.markdown(f'<div class="{cls}"><h4>{title}</h4><p>{body}</p></div>', unsafe_allow_html=True)
    for i in issues:
        st.error(i)
    for w in warns:
        st.warning(w)

    # ── key dates
    st.markdown("#### 📅  Key Dates")
    kd1, kd2, kd3 = st.columns(3)
    kd1.metric("Earliest ILR Eligibility", eng.earliest_ilr.strftime("%d %b %Y"))
    kd2.metric("Earliest Application (−28 days)", eng.earliest_application.strftime("%d %b %Y"))
    kd3.metric("UK Residence Rate", f"{eng.residence_pct:.1f}%")

    # ── tabbed detail
    tab1, tab2, tab3, tab4 = st.tabs(
        ["📋 Trip Breakdown", "📈 Timeline Chart", "🔄 Rolling Window", "📅 Year-by-Year"]
    )

    with tab1:
        _tab_trips(eng)
    with tab2:
        _tab_timeline(eng)
    with tab3:
        _tab_rolling(eng, max_roll, ws, we, risky)
    with tab4:
        _tab_yearly(eng)

    _export(eng, max_roll, budget, status, issues, warns)
    _cta()


def _tab_trips(eng: ILRAbsenceEngine):
    rows = eng.trip_table()
    if not rows:
        st.info("No trips entered.")
        return
    df = pd.DataFrame(rows)
    df["Departure"] = pd.to_datetime(df["Departure"]).dt.strftime("%d %b %Y")
    df["Return"] = pd.to_datetime(df["Return"]).dt.strftime("%d %b %Y")
    st.dataframe(
        df,
        width='stretch',
        hide_index=True,
        column_config={
            "Days Absent": st.column_config.ProgressColumn("Days Absent", min_value=0, max_value=180, format="%d days")
        },
    )
    m1, m2, m3 = st.columns(3)
    n = len(rows)
    m1.metric("Total Trips", n)
    m2.metric("Average Trip Length", f"{eng.total_absent / n:.0f} days" if n else "—")
    m3.metric("UK Residence Rate", f"{eng.residence_pct:.1f}%")


def _tab_timeline(eng: ILRAbsenceEngine):
    md = eng.monthly_data()
    if md.empty:
        st.info("No data to display.")
        return
    fig = go.Figure()
    fig.add_trace(go.Bar(x=md["Month"], y=md["Days Absent"], name="Days Absent", marker_color="#e74c3c", opacity=0.85))
    fig.add_trace(go.Bar(x=md["Month"], y=md["Days in UK"], name="Days in UK", marker_color="#2ecc71", opacity=0.85))
    fig.update_layout(
        barmode="stack",
        title="Monthly UK Presence / Absence",
        xaxis_title="Month",
        yaxis_title="Days",
        height=420,
        template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    st.plotly_chart(fig, width='stretch')


def _tab_rolling(eng: ILRAbsenceEngine, max_days, ws, we, risky):
    st.markdown(
        "The Home Office checks that you have **not been absent for more than 180 days "
        "in any 12-calendar-month period** during your qualifying residence."
    )
    if max_days == 0:
        st.success("No absences recorded — nothing to analyse.")
        return

    fig = go.Figure(
        go.Indicator(
            mode="gauge+number+delta",
            value=max_days,
            delta={"reference": 180, "increasing": {"color": "#e74c3c"}, "decreasing": {"color": "#2ecc71"}},
            title={
                "text": (
                    f"Worst 12-Month Window<br>"
                    f"<span style='font-size:.7em;color:#666'>"
                    f"{ws:%d %b %Y} → {we:%d %b %Y}</span>"
                )
            },
            gauge={
                "axis": {"range": [0, 250], "tickwidth": 1},
                "bar": {"color": "#667eea"},
                "steps": [
                    {"range": [0, 120], "color": "#d4edda"},
                    {"range": [120, 160], "color": "#fff3cd"},
                    {"range": [160, 180], "color": "#ffe0b2"},
                    {"range": [180, 250], "color": "#f8d7da"},
                ],
                "threshold": {"line": {"color": "red", "width": 4}, "thickness": 0.75, "value": 180},
            },
        )
    )
    fig.update_layout(height=320)
    st.plotly_chart(fig, width='stretch')

    if risky:
        st.markdown("#### ⚠️  High-Risk Windows (>150 days)")
        rdf = pd.DataFrame(risky)
        rdf["start"] = pd.to_datetime(rdf["start"]).dt.strftime("%d %b %Y")
        rdf["end"] = pd.to_datetime(rdf["end"]).dt.strftime("%d %b %Y")
        rdf.columns = ["Window Start", "Window End", "Days Absent"]
        st.dataframe(rdf.drop_duplicates(subset="Days Absent").head(10), width='stretch', hide_index=True)


def _tab_yearly(eng: ILRAbsenceEngine):
    yb = eng.yearly_breakdown()
    if not yb:
        st.info("No absences to display.")
        return
    df = pd.DataFrame(yb)
    fig = px.bar(
        df,
        x="Year",
        y=["Days Absent", "Days in UK"],
        barmode="stack",
        color_discrete_map={"Days Absent": "#e74c3c", "Days in UK": "#2ecc71"},
        title="Absences by Calendar Year",
    )
    fig.update_layout(height=360, template="plotly_white", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    st.plotly_chart(fig, width='stretch')
    st.dataframe(
        df,
        width='stretch',
        hide_index=True,
        column_config={"Absence %": st.column_config.ProgressColumn("Absence %", min_value=0, max_value=100, format="%.1f%%")},
    )


# ── export ───────────────────────────────────────────────────


def _export(eng: ILRAbsenceEngine, max_roll, budget, status, issues, warns):
    st.markdown("### 📥  Export Your Report")
    ec1, ec2 = st.columns(2)

    with ec1:
        buf = BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as w:
            pd.DataFrame(
                {
                    "Metric": [
                        "Visa Start",
                        "Planned ILR Date",
                        "Earliest ILR Eligibility",
                        "Earliest Application (−28 days)",
                        "Total Days Absent",
                        "Days in UK",
                        "UK Residence %",
                        "Worst 12-Month Window",
                        "Longest Single Trip",
                        "Safe Days Remaining",
                        "Status",
                    ],
                    "Value": [
                        str(eng.visa_start),
                        str(eng.planned_ilr),
                        str(eng.earliest_ilr),
                        str(eng.earliest_application),
                        eng.total_absent,
                        eng.days_in_uk,
                        f"{eng.residence_pct:.1f}%",
                        max_roll,
                        eng.longest_trip()[0],
                        budget["effective"],
                        status,
                    ],
                }
            ).to_excel(w, sheet_name="Summary", index=False)

            tt = eng.trip_table()
            if tt:
                pd.DataFrame(tt).to_excel(w, sheet_name="Trips", index=False)
            yb = eng.yearly_breakdown()
            if yb:
                pd.DataFrame(yb).to_excel(w, sheet_name="Yearly", index=False)
            findings = [{"Type": "Issue", "Detail": i} for i in issues] + [{"Type": "Warning", "Detail": w_} for w_ in warns]
            if findings:
                pd.DataFrame(findings).to_excel(w, sheet_name="Findings", index=False)

        st.download_button(
            "📊  Download Excel Report",
            data=buf.getvalue(),
            file_name=f"ilr_absence_report_{date.today()}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width='stretch',
        )

    with ec2:
        tt = eng.trip_table()
        if tt:
            st.download_button(
                "📋  Download Trips CSV",
                data=pd.DataFrame(tt).to_csv(index=False),
                file_name=f"ilr_trips_{date.today()}.csv",
                mime="text/csv",
                width='stretch',
            )


# ── CTA ──────────────────────────────────────────────────────


def _cta():
    st.markdown(
        """
    <div class="cta-box">
        <h3 style="color:#fff;margin:0">🎓 Want a Professional Assessment?</h3>
        <p style="color:rgba(255,255,255,.9);max-width:600px;margin:.75rem auto">
            OISC-registered immigration advisers can review your case, verify your absences,
            and prepare your ILR application with confidence.
        </p>
        <p style="color:rgba(255,255,255,.8);font-size:.9rem;margin-top:1rem">
            ✓ Personalised eligibility review &nbsp;|&nbsp;
            ✓ Document checklist &nbsp;|&nbsp;
            ✓ Application support
        </p>
    </div>
    """,
        unsafe_allow_html=True,
    )


# ── FAQ (SEO-rich) ───────────────────────────────────────────


def _faq():
    st.markdown("---")
    st.markdown("## ❓  Frequently Asked Questions")

    with st.expander("What is the 180-day rule for ILR?"):
        st.markdown(
            """
The UK Home Office requires that you have not spent more than **180 days outside the UK
in any rolling 12-calendar-month period** during your qualifying residence.

**Important:** The Home Office uses **calendar months** (not a fixed 365 days) to define
a 12-month period.  This calculator mirrors that method.
"""
        )

    with st.expander("How are travel days counted?"):
        st.markdown(
            """
The Home Office counts **both the day you depart and the day you return** as days
outside the UK.  If you fly out on 1 January and return on 10 January, that is
**10 days** absent.

Some advisers argue the departure day should not count if you were in the UK most
of it, but the safest approach is to count both ends.
"""
        )

    with st.expander("What happens if I breach the 180-day rule?"):
        st.markdown(
            """
A breach does not automatically mean refusal, but it is a major hurdle.  Options include:

1. **Reset your qualifying period** — start counting from a later date.
2. **Argue exceptional circumstances** — compassionate / medical / emergency reasons.
3. **Switch to the 10-year route** — if your total absences fit within 548 days.

Always consult an immigration solicitor if you have exceeded the limit.
"""
        )

    with st.expander("5-year vs 10-year route — what's the difference?"):
        st.markdown(
            """
| | 5-Year Route | 10-Year Route |
|---|---|---|
| **Qualifying period** | 5 years | 10 years |
| **Rolling limit** | 180 days / 12 months | 180 days / 12 months |
| **Total absence cap** | No explicit cap | 548 days |
| **Typical visas** | Skilled Worker, Spouse, Innovator | Long Residence |
"""
        )

    with st.expander("When can I apply for ILR?"):
        st.markdown(
            """
You may apply **up to 28 days before** you complete your qualifying period.
For example, if your 5-year period ends on 1 March 2026 you can submit from
1 February 2026.

This calculator shows both the eligibility date and the earliest application date.
"""
        )

    with st.expander("Can time on different visas count?"):
        st.markdown(
            """
For the **10-year Long Residence** route, time on most visa types counts as long as
you have had continuous *lawful* residence.  For **5-year routes** you generally
need to have been on the same (or a qualifying) visa category for the full period.

Some route-switches preserve your qualifying period — check the guidance for your
specific visa type.
"""
        )


# ── footer ───────────────────────────────────────────────────


def _footer():
    st.markdown(
        """
    <div class="footer">
        <p><strong>Disclaimer:</strong> This tool is for informational purposes only and does
        not constitute legal advice.  Immigration rules change frequently.  Always verify with
        the <a href="https://www.gov.uk/indefinite-leave-to-remain" target="_blank">official
        Home Office guidance</a> and consult a qualified immigration adviser.</p>
        <p style="margin-top:.5rem">© 2026 ILR Absence Calculator · All rights reserved.</p>
    </div>
    """,
        unsafe_allow_html=True,
    )


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════


def main():
    _header()
    cfg, visa_start, planned_ilr = _sidebar()
    trips = _trip_editor()

    if trips:
        eng = ILRAbsenceEngine(cfg, visa_start, planned_ilr, trips)
        if eng.trips:  # at least one valid trip
            _show_results(eng)
        else:
            st.warning("The trips entered have invalid dates (departure must be ≤ return).  Please correct them.")
    else:
        st.info("👆  Add at least one trip above to see your absence analysis.")

    _faq()
    _footer()


if __name__ == "__main__":
    main()
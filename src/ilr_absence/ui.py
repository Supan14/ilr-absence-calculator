"""
Streamlit UI components: header, sidebar, trip editor, results, FAQ, footer.
"""

from datetime import date
from io import BytesIO, StringIO

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from dateutil.relativedelta import relativedelta

from ilr_absence.config import COUNTRIES, REASONS, ROUTES
from ilr_absence.engine import ILRAbsenceEngine


# ── advertisements ───────────────────────────────────────────


def render_ad_script(pub_id: str) -> None:
    """Inject the AdSense verification meta tag and async loader into the page."""
    st.markdown(
        f"""<script>
(function(){{
  var m = document.createElement('meta');
  m.name = 'google-adsense-account';
  m.content = '{pub_id}';
  document.head.appendChild(m);
}})();
</script>
<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js\
?client={pub_id}" crossorigin="anonymous"></script>""",
        unsafe_allow_html=True,
    )


def render_ad_unit(pub_id: str, slot_id: str, ad_format: str = "auto") -> None:
    """Render a responsive Google AdSense display ad unit."""
    st.markdown(
        f"""
<div style="text-align:center;margin:1.25rem 0;min-height:90px">
  <ins class="adsbygoogle"
       style="display:block"
       data-ad-client="{pub_id}"
       data-ad-slot="{slot_id}"
       data-ad-format="{ad_format}"
       data-full-width-responsive="true"></ins>
  <script>(adsbygoogle = window.adsbygoogle || []).push({{}});</script>
</div>""",
        unsafe_allow_html=True,
    )


# ── header ───────────────────────────────────────────────────


def render_header():
    st.markdown(
        """
    <div style="text-align:center;padding:1.5rem 0 1rem">
        <div style="display:inline-flex;align-items:center;gap:.6rem;margin-bottom:.5rem">
            <span style="font-size:2.8rem">🇬🇧</span>
            <h1 style="font-size:2.4rem;font-weight:800;margin:0;
                       background:linear-gradient(135deg,#667eea,#764ba2);
                       -webkit-background-clip:text;-webkit-text-fill-color:transparent">
                ILR Absence Calculator
            </h1>
        </div>
        <p style="font-size:1.05rem;color:#555;max-width:620px;margin:.4rem auto 0;line-height:1.6">
            Track your UK absences, check the <strong>180-day rule</strong>, and verify your
            <strong>Indefinite Leave to Remain</strong> eligibility — instantly and privately.
        </p>
        <div style="display:flex;justify-content:center;gap:1.5rem;margin-top:1rem;flex-wrap:wrap">
            <span style="font-size:.85rem;color:#667eea;font-weight:600">✓ 5-year &amp; 10-year routes</span>
            <span style="font-size:.85rem;color:#667eea;font-weight:600">✓ Rolling 12-month window</span>
            <span style="font-size:.85rem;color:#667eea;font-weight:600">✓ No data stored</span>
        </div>
    </div>
    """,
        unsafe_allow_html=True,
    )


# ── sidebar ──────────────────────────────────────────────────


def render_sidebar() -> tuple[dict, date, date]:
    with st.sidebar:
        st.markdown("### ⚙️ Configuration")
        route_name = st.selectbox("ILR Route", list(ROUTES.keys()), help="Select your visa route to ILR")
        cfg = ROUTES[route_name]
        st.caption(cfg["desc"])
        st.divider()

        # Promote pending values imported from CSV before widgets register their keys
        if "visa_start_date_pending" in st.session_state:
            st.session_state["visa_start_date"] = st.session_state.pop("visa_start_date_pending")
        if "planned_ilr_date_pending" in st.session_state:
            st.session_state["planned_ilr_date"] = st.session_state.pop("planned_ilr_date_pending")

        # Seed defaults only when the key is absent so widgets never get both
        # a value= argument and a session-state value at the same time.
        if "visa_start_date" not in st.session_state:
            st.session_state["visa_start_date"] = date.today() - relativedelta(years=cfg["years"])
        if "planned_ilr_date" not in st.session_state:
            st.session_state["planned_ilr_date"] = (
                st.session_state["visa_start_date"] + relativedelta(years=cfg["years"])
            )

        c1, c2 = st.columns(2)
        with c1:
            visa_start = st.date_input(
                "Visa Start Date",
                key="visa_start_date",
                help="Date your current qualifying visa started",
            )
        with c2:
            planned_ilr = st.date_input(
                "Planned ILR Date",
                key="planned_ilr_date",
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


# ── CSV import helper ─────────────────────────────────────────


def _trips_from_csv(content: bytes) -> tuple[list[dict], date | None, date | None]:
    """Parse a CSV produced by the export button back into trip dicts and optional visa dates."""
    raw = content.decode("utf-8", errors="replace")
    visa_start: date | None = None
    planned_ilr: date | None = None

    lines = raw.splitlines()
    for line in lines:
        if line.startswith("# visa_start,"):
            try:
                visa_start = pd.to_datetime(line.split(",", 1)[1].strip()).date()
            except Exception:
                pass
        elif line.startswith("# planned_ilr,"):
            try:
                planned_ilr = pd.to_datetime(line.split(",", 1)[1].strip()).date()
            except Exception:
                pass

    csv_body = "\n".join(l for l in lines if not l.startswith("#"))
    df = pd.read_csv(StringIO(csv_body))
    df.columns = [c.strip() for c in df.columns]
    trips = []
    for _, row in df.iterrows():
        try:
            dep = pd.to_datetime(row["Departure"]).date()
            ret = pd.to_datetime(row["Return"]).date()
        except Exception:
            continue
        if dep <= ret:
            trips.append({
                "departure": dep,
                "return": ret,
                "destination": str(row.get("Destination") or ""),
                "reason": str(row.get("Reason") or ""),
            })
    return trips, visa_start, planned_ilr


# ── trip editor ──────────────────────────────────────────────


def render_trip_editor() -> list[dict]:
    st.markdown("### ✈️  Your Trips Outside the UK")
    st.caption("Add every trip where you left the UK, including the day you departed and the day you returned.")

    if "trips" not in st.session_state:
        st.session_state.trips = []

    # ── CSV import ───────────────────────────────────────────
    with st.expander("📂  Import trips from a previously exported CSV"):
        uploaded = st.file_uploader(
            "Upload CSV",
            type="csv",
            label_visibility="collapsed",
            help="Upload the CSV you downloaded from a previous session to restore your trips.",
        )
        if uploaded is not None:
            file_key = f"{uploaded.name}_{uploaded.size}"
            if st.session_state.get("_last_imported_file") != file_key:
                imported, imported_vs, imported_pilr = _trips_from_csv(uploaded.read())
                if imported:
                    st.session_state["_last_imported_file"] = file_key
                    st.session_state.trips = imported
                    if imported_vs is not None:
                        st.session_state["visa_start_date_pending"] = imported_vs
                    if imported_pilr is not None:
                        st.session_state["planned_ilr_date_pending"] = imported_pilr
                    st.success(f"Imported {len(imported)} trip(s).")
                    st.rerun()
                else:
                    st.error("No valid trips found in the file. Make sure it has Departure and Return columns.")
            else:
                st.success(f"{len(st.session_state.trips)} trip(s) loaded from CSV.")

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


# ── results ──────────────────────────────────────────────────


def render_results(eng: ILRAbsenceEngine):
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

    _render_export(eng, max_roll, budget, status, issues, warns)


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


def _render_export(eng: ILRAbsenceEngine, max_roll, budget, status, issues, warns):
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
            csv_metadata = f"# visa_start,{eng.visa_start}\n# planned_ilr,{eng.planned_ilr}\n"
            st.download_button(
                "📋  Download Trips CSV",
                data=csv_metadata + pd.DataFrame(tt).to_csv(index=False),
                file_name=f"ilr_trips_{date.today()}.csv",
                mime="text/csv",
                width='stretch',
            )


# ── FAQ ──────────────────────────────────────────────────────


def render_faq():
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


def render_footer():
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

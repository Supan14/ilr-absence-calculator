"""
UK ILR Absence Calculator
─────────────────────────
Track UK absences and check eligibility for Indefinite Leave to Remain (ILR).

Rules implemented:
    • 180-day rolling 12-calendar-month window (all routes)
    • Total absence cap (10-year Long Residence: 548 days)
    • Single-trip duration check (no trip > 6 months)
"""

import streamlit as st

from ilr_absence.config import AD_PUB_ID, AD_SLOTS, CSS
from ilr_absence.engine import ILRAbsenceEngine
from ilr_absence.ui import render_ad_script, render_ad_unit, render_footer, render_faq, render_header, render_results, render_sidebar, render_trip_editor

st.set_page_config(
    page_title="UK ILR Absence Calculator - Check Your Eligibility",
    page_icon="🇬🇧",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(CSS, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════


def main():
    render_ad_script(AD_PUB_ID)
    render_header()
    render_ad_unit(AD_PUB_ID, AD_SLOTS["header"])   # leaderboard below header
    cfg, visa_start, planned_ilr = render_sidebar()
    trips = render_trip_editor()

    if trips:
        eng = ILRAbsenceEngine(cfg, visa_start, planned_ilr, trips)
        if eng.trips:  # at least one valid trip
            render_results(eng)
            render_ad_unit(AD_PUB_ID, AD_SLOTS["results"])  # rectangle after report
        else:
            st.warning("The trips entered have invalid dates (departure must be ≤ return).  Please correct them.")
    else:
        st.info("👆  Add at least one trip above to see your absence analysis.")

    render_ad_unit(AD_PUB_ID, AD_SLOTS["pre_faq"])  # banner before FAQ
    render_faq()
    render_footer()


if __name__ == "__main__":
    main()

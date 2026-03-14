"""
Static configuration: routes, constants, and CSS.
"""

import streamlit as st
from pycountry import countries

COUNTRIES: list[str] = sorted(c.name for c in countries)

REASONS: list[str] = ["Holiday", "Family Visit", "Business", "Emergency", "Medical", "Other"]

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

# ── Advertisement Configuration ─────────────────────────────
# Credentials are loaded from Streamlit secrets (.streamlit/secrets.toml).
# That file is git-ignored.  See .streamlit/secrets.toml.example for the
# required keys.  When a key is absent (e.g. local dev without secrets),
# ads are silently disabled so the app still runs normally.

def _secret(key: str, default: str = "") -> str:
    try:
        return st.secrets.get(key, default)    # type: ignore[attr-defined]
    except Exception:
        return default

AD_PUB_ID: str = _secret("ADSENSE_PUB_ID")

AD_SLOTS: dict[str, str] = {
    "header":  _secret("ADSENSE_SLOT_HEADER"),
    "results": _secret("ADSENSE_SLOT_RESULTS"),
    "pre_faq": _secret("ADSENSE_SLOT_PRE_FAQ"),
}

CSS: str = """
<style>
  .main .block-container{padding-top:1.5rem}
  div[data-testid="stMetric"]{
      background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);
      padding:1rem 1.25rem;border-radius:12px;
      box-shadow:0 4px 15px rgba(102,126,234,.3)}
  div[data-testid="stMetric"] label{color:rgba(255,255,255,.85)!important}
  div[data-testid="stMetric"] [data-testid="stMetricValue"]{color:#fff!important}
  div[data-testid="stMetric"] [data-testid="stMetricDelta"]{color:rgba(255,255,255,.9)!important}
  .risk-low{background:#d4edda;border-left:5px solid #28a745;padding:1rem;border-radius:8px;margin:1rem 0;color:#155724}
  .risk-low h4,.risk-low p{color:#155724!important}
  .risk-med{background:#fff3cd;border-left:5px solid #ffc107;padding:1rem;border-radius:8px;margin:1rem 0;color:#856404}
  .risk-med h4,.risk-med p{color:#856404!important}
  .risk-high{background:#f8d7da;border-left:5px solid #dc3545;padding:1rem;border-radius:8px;margin:1rem 0;color:#721c24}
  .risk-high h4,.risk-high p{color:#721c24!important}
  .footer{text-align:center;color:#999;padding:2rem 0;font-size:.85rem;
          border-top:1px solid #eee;margin-top:3rem}
  #MainMenu{visibility:hidden}
  footer{visibility:hidden}
  .stTabs [data-baseweb="tab-list"]{gap:8px}
</style>
"""

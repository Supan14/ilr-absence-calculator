"""
Core calculation engine for UK ILR absence rules.
"""

import bisect
from datetime import date, timedelta

import pandas as pd
from dateutil.relativedelta import relativedelta


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
        qualifying_period_warn = False
        if today < self.earliest_ilr:
            rem = (self.earliest_ilr - today).days
            warns.append(f"📅 **Qualifying period incomplete**: {rem} days until {self.earliest_ilr:%d %b %Y}.")
            qualifying_period_warn = True

        # Only escalate to CAUTION if there are warnings beyond the qualifying period
        non_qp_warns = [w for w in warns if not w.startswith("📅")]
        status = "FAIL" if issues else ("CAUTION" if non_qp_warns else "PASS")
        return status, issues, warns

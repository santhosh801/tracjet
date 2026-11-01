"""
Location + experience send filters.

  - No cities selected ("All Cities")      → no location restriction
  - "All Experience"                       → no experience restriction
  - A specific experience range [lo, hi]   → the job's required range must lie inside it
                                             (open-ended "5+ yrs" only fits ranges with no upper bound)
Jobs that fail a filter are never deleted — they are marked "Filtered Out – …".
"""
from dataclasses import dataclass, field

import knowledge as kb

ELIGIBLE = "Eligible"
FILTERED_LOCATION = "Filtered Out – Location"
FILTERED_EXPERIENCE = "Filtered Out – Experience"
FILTERED_BOTH = "Filtered Out – Location & Experience"


@dataclass
class FilterConfig:
    cities: list = field(default_factory=list)   # empty = All Cities
    exp_min: float | None = None                  # both None = All Experience
    exp_max: float | None = None
    exp_mode: str = "All Experience"

    @property
    def all_cities(self) -> bool:
        return not self.cities

    @property
    def all_experience(self) -> bool:
        return self.exp_min is None and self.exp_max is None

    @classmethod
    def from_settings(cls, d: dict | None) -> "FilterConfig":
        d = d or {}
        mode = d.get("exp_mode") or "All Experience"
        lo, hi = d.get("exp_min"), d.get("exp_max")
        for label, blo, bhi in kb.EXPERIENCE_BUCKETS:
            if label == mode:
                lo, hi = blo, bhi
                break
        return cls(cities=list(d.get("cities") or []),
                   exp_min=float(lo) if lo not in (None, "") else None,
                   exp_max=float(hi) if hi not in (None, "") else None, exp_mode=mode)

    def to_settings(self) -> dict:
        return {"cities": list(self.cities), "exp_mode": self.exp_mode, "exp_min": self.exp_min,
                "exp_max": self.exp_max}

    def describe(self) -> str:
        loc = "All Cities" if self.all_cities else ", ".join(self.cities)
        if self.all_experience:
            exp = "All Experience"
        elif self.exp_max is None:
            exp = f"{self.exp_min:g}+ years"
        else:
            exp = f"{(self.exp_min or 0):g}–{self.exp_max:g} years"
        return f"Location: {loc}  |  Experience: {exp}"


def job_cities(record: dict) -> list[str]:
    raw = record.get("location_cities")
    if isinstance(raw, list):
        cities = raw
    elif raw:
        import json
        try:
            cities = json.loads(raw)
        except Exception:
            cities = []
    else:
        cities = []
    return cities or kb.detect_cities(record.get("location") or "")


def location_matches(record: dict, cfg: FilterConfig) -> tuple[bool, str]:
    if cfg.all_cities:
        return True, "All Cities"
    cities = job_cities(record)
    if not cities:
        return False, "job location not stated"
    hit = [c for c in cities if c in cfg.cities]
    return (True, ", ".join(hit)) if hit else (False, f"job is in {', '.join(cities)}")


def _job_range(record: dict):
    lo, hi = record.get("exp_min"), record.get("exp_max")
    if lo is None and hi is None and record.get("experience"):
        from jd_analyzer import parse_experience
        lo, hi, _ = parse_experience("Experience: " + str(record["experience"]))
    return lo, hi


def experience_matches(record: dict, cfg: FilterConfig) -> tuple[bool, str]:
    if cfg.all_experience:
        return True, "All Experience"
    lo, hi = _job_range(record)
    if lo is None:
        return False, "experience not stated in the job post"
    f_lo = cfg.exp_min if cfg.exp_min is not None else 0.0
    if lo < f_lo:
        return False, f"job needs {lo:g}+ yrs, below the {f_lo:g} yr minimum"
    if cfg.exp_max is not None:
        if hi is None:
            return False, f"job is open-ended ({lo:g}+ yrs), above the {cfg.exp_max:g} yr maximum"
        if hi > cfg.exp_max:
            return False, f"job range {lo:g}–{hi:g} yrs exceeds the {cfg.exp_max:g} yr maximum"
    return True, "in range"


def evaluate_filters(record: dict, cfg: FilterConfig) -> tuple[str, list[str]]:
    loc_ok, loc_reason = location_matches(record, cfg)
    exp_ok, exp_reason = experience_matches(record, cfg)
    reasons = []
    if not loc_ok:
        reasons.append("Location: " + loc_reason)
    if not exp_ok:
        reasons.append("Experience: " + exp_reason)
    if loc_ok and exp_ok:
        return ELIGIBLE, reasons
    if not loc_ok and not exp_ok:
        return FILTERED_BOTH, reasons
    return (FILTERED_LOCATION if not loc_ok else FILTERED_EXPERIENCE), reasons

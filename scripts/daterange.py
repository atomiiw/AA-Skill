#!/usr/bin/env python3
"""
Date-range selector logic for the split-bills skill (Stage 1). Month granularity
only. The selectable window is the current month and the 3 months before it
(4 months max).

Functions-only module — no CLI. The front door is ../run.py, which calls these
and prints their return values as JSON:
  start_years(today)              -> list[int]  selectable start years
                                     (current year first; 2 only when Jan-Mar)
  start_months(today, year)       -> list[{label,value}]  window months in year
  end_options(today, start)       -> list[{label,value}]  start..current month
  resolve(today, start, end)      -> {since, until}  (until=today if end is the
                                     current month, never the future)

`today` is a datetime.date; `start`/`end` are "YYYY-MM" strings.
"""

import calendar
from datetime import date


def add_months(y, m, delta):
    idx = y * 12 + (m - 1) + delta
    return idx // 12, idx % 12 + 1


def month_label(y, m):
    return f"{calendar.month_name[m]} {y}"


def window(today):
    """Current month + 3 prior, oldest first -> [(y, m), ...] (4 entries)."""
    return [add_months(today.year, today.month, -i) for i in range(3, -1, -1)]


def start_years(today):
    """Selectable start years, current year first."""
    return sorted({y for y, _ in window(today)}, reverse=True)


def start_months(today, year):
    """Window months that fall in `year`, oldest first."""
    return [
        {"label": month_label(y, m), "value": f"{y}-{m:02d}"} for y, m in window(today) if y == year
    ]


def end_options(today, start):
    """Every month from `start` through the current month, inclusive."""
    sy, sm = map(int, start.split("-"))
    opts, (y, m) = [], (sy, sm)
    while (y, m) <= (today.year, today.month):
        opts.append({"label": month_label(y, m), "value": f"{y}-{m:02d}"})
        y, m = add_months(y, m, 1)
    return opts


def resolve(today, start, end):
    """Resolve start/end months to concrete --since/--until dates.

    since = 1st of the start month; until = last day of the end month, or today
    if the end month is the current month (never the future).
    """
    sy, sm = map(int, start.split("-"))
    ey, em = map(int, end.split("-"))
    since = date(sy, sm, 1)
    if (ey, em) == (today.year, today.month):
        until = today
    else:
        until = date(ey, em, calendar.monthrange(ey, em)[1])
    return {"since": since.isoformat(), "until": until.isoformat()}

# core/maintenance_logic.py
import pandas as pd
from datetime import datetime
from core.col_utils import find_column_by_keywords

def map_columns(df: pd.DataFrame) -> dict:
    cols = list(df.columns)
    mapping = {
        "equipment": find_column_by_keywords(cols, ["equipment", "equipment_name", "equipment name", "item", "component", "equipment id", "part", "equipment\nname"]),
        "last_maintenance": find_column_by_keywords(cols, ["last maintenance", "last_maintenance", "last serviced", "completed date", "completion", "completion date", "last service", "work performed", "created"]),
        "maintenance_date": find_column_by_keywords(cols, ["planned", "planned date", "planned_date", "planned 2nd", "planned date"]),
        "failure_text": find_column_by_keywords(cols, ["fault", "failure", "issue", "problem", "report"]),
        "failure_count": find_column_by_keywords(cols, ["failure_count", "failures", "fault_count", "faults", "no_of_failures"]),
        "age": find_column_by_keywords(cols, ["age", "equipment_age", "years"]),
        "order_item": find_column_by_keywords(cols, ["order", "order item", "order_item", "order_no", "order code"]),
        "stock": find_column_by_keywords(cols, ["stock", "current_stock", "on_hand", "quantity", "qty"]),
        "order_date": find_column_by_keywords(cols, ["order date", "order_date", "delivery date", "delivery"]),
    }
    return mapping

def last_maintenance_per_equipment(df: pd.DataFrame, mapping: dict) -> pd.DataFrame:
    """
    Returns a dataframe with equipment and their last maintenance datetime (most recent).
    """
    equip_col = mapping.get("equipment")
    last_cols = [c for c in df.columns if "date" in c.lower() or "created" in c.lower() or "completion" in c.lower() or "serv" in c.lower()]
    if not equip_col or not last_cols:
        # fallback: try looking for planned/created/etc
        last_cols = [mapping.get("last_maintenance"), mapping.get("maintenance_date")]
    dates = []
    # For each equipment, find the latest date across candidate date columns
    grouped = []
    for equip, group in df.groupby(equip_col) if equip_col in df.columns else []:
        candidate_dates = pd.to_datetime(pd.Series(dtype='datetime64[ns]'))
        for c in last_cols:
            if c and c in group.columns:
                candidate_dates = candidate_dates.append(pd.to_datetime(group[c], errors='coerce'), ignore_index=True)
        if not candidate_dates.empty:
            last_dt = candidate_dates.max()
            grouped.append({"equipment": equip, "last_maintenance_date": last_dt})
    return pd.DataFrame(grouped)

def find_missing_maintenance(df: pd.DataFrame, months: int = 6) -> pd.DataFrame or str:
    m = map_columns(df)
    equip_col = m.get("equipment")
    # try to find last maintenance directly in common columns
    candidates = [m.get("last_maintenance"), m.get("maintenance_date")]
    # build a helper frame:
    df2 = df.copy()
    # pick the most plausible date column for last maintenance
    date_col = None
    for cand in candidates:
        if cand and cand in df2.columns:
            date_col = cand
            break
    # if still none, try to pick most date-like column by name
    if not date_col:
        for c in df2.columns:
            if any(k in c.lower() for k in ("last", "completion", "completed", "date", "serv")):
                date_col = c
                break
    if not equip_col or not date_col:
        return "Required columns for maintenance check not found."

    df2.loc[:, date_col] = pd.to_datetime(df2[date_col], errors="coerce")
    cutoff = pd.Timestamp.now() - pd.DateOffset(months=months)
    missing = df2[df2[date_col].isna() | (df2[date_col] < cutoff)].copy()
    if missing.empty:
        return "All equipment has maintenance within last {} months.".format(months)

    # build actionable summary
    summary_cols = [equip_col, date_col]
    summary_cols = [c for c in summary_cols if c in missing.columns]
    missing = missing[summary_cols].drop_duplicates()
    # compute days since maintenance (NaT -> large number)
    if date_col in missing.columns:
        missing.loc[:, "last_maintenance_date"] = pd.to_datetime(missing[date_col], errors="coerce")
        missing.loc[:, "days_since_last"] = (pd.Timestamp.now() - missing["last_maintenance_date"]).dt.days
        missing.loc[:, "days_since_last"] = missing["days_since_last"].fillna(99999).astype(int)
        missing = missing.sort_values("days_since_last", ascending=False)
    return missing.reset_index(drop=True)

def predict_replacement(df: pd.DataFrame,
                        months_window:int = 6,
                        maintenance_count_threshold:int = 4,
                        failure_count_threshold:int = 3) -> pd.DataFrame or str:
    """
    Predict replacement if:
    - an equipment had >= maintenance_count_threshold maintenance actions within last months_window months OR
    - failure_count (if present) >= failure_count_threshold OR
    - repeated entries with short intervals (approximation)
    """
    m = map_columns(df)
    equip_col = m.get("equipment")
    # choose date column candidates:
    date_candidates = [m.get("last_maintenance"), m.get("maintenance_date")]
    # choose failure col
    failure_col = m.get("failure_count") or m.get("failure_text")
    if not equip_col:
        return "Equipment column not found."

    df2 = df.copy()
    # find a date column to use
    date_col = None
    for c in date_candidates:
        if c and c in df2.columns:
            date_col = c
            break
    if not date_col:
        # try to find any date-like column
        for c in df2.columns:
            if any(k in c.lower() for k in ("date", "created", "completion", "serv")):
                date_col = c
                break
    if not date_col:
        return "No date column found to evaluate maintenance frequency."

    df2.loc[:, date_col] = pd.to_datetime(df2[date_col], errors="coerce")
    window_start = pd.Timestamp.now() - pd.DateOffset(months=months_window)

    # count maintenance actions per equipment within window
    recent = df2[df2[date_col] >= window_start].copy()
    counts = recent.groupby(equip_col).size().rename("maint_actions").reset_index()
    # failure counts (if numeric)
    if failure_col and failure_col in df2.columns:
        df2.loc[:, failure_col] = pd.to_numeric(df2[failure_col], errors="coerce").fillna(0)
        failures = df2.groupby(equip_col)[failure_col].sum().rename("failure_count").reset_index()
        counts = counts.merge(failures, on=equip_col, how="left")
    else:
        counts["failure_count"] = 0

    # select those that meet thresholds
    counts.loc[:, "replace_flag"] = ((counts["maint_actions"] >= maintenance_count_threshold) |
                                     (counts["failure_count"] >= failure_count_threshold))
    risky = counts[counts["replace_flag"]].sort_values(["failure_count", "maint_actions"], ascending=False)
    if risky.empty:
        return "No equipment predicted for replacement in the next {} months (based on thresholds).".format(months_window)
    return risky.reset_index(drop=True)

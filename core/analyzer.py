# core/analyzer.py
import pandas as pd
import numpy as np


###############################################################################
# 🟦 ROBUST DATE PARSING
###############################################################################
def _try_date_parse(df):
    # avoid unnecessary copying unless we must modify
    df = df.copy()
    date_like_cols = []

    for c in df.columns:
        col = str(c).lower()
        if (
            "date" in col
            or "done" in col
            or "due" in col
            or "last" in col
            or "maintenance" in col
        ):
            date_like_cols.append(c)

    for c in date_like_cols:
        df[c] = pd.to_datetime(df[c], errors="coerce", dayfirst=True)

    return df


###############################################################################
# 🟦 ORIGINAL PRACTICAL INSIGHTS (UNCHANGED, EFFICIENT)
###############################################################################
def analyze_practical_insights(loaded_files: dict, element_name_col: str = "Element Name"):
    histories = []
    planned_df = None
    orders_df = None

    for name, df in loaded_files.items():
        lname = name.lower()
        if "history" in lname:
            histories.append(_try_date_parse(df))
        elif "planned" in lname:
            planned_df = _try_date_parse(df)
        elif "order" in lname:
            orders_df = _try_date_parse(df)

    if histories:
        hist = pd.concat(histories, ignore_index=True, sort=False)
    else:
        hist = pd.DataFrame()

    # Determine equipment column safely
    element_col = None
    for df in [hist, planned_df, orders_df]:
        if df is not None and not df.empty:
            for c in df.columns:
                if element_name_col.lower() in str(c).lower():
                    element_col = c
                    break
            if element_col:
                break

    if element_col is None and not hist.empty:
        element_col = hist.columns[0]  # fallback

    TODAY = pd.Timestamp.now()

    # Missing Maintenance
    missing = pd.DataFrame(columns=["Equipment Name", "last_maintenance_date", "days_since_last"])
    if not hist.empty and element_col:
        # detect any date column
        date_cols = [c for c in hist.columns if "date" in c.lower() or "done" in c.lower()]
        if date_cols:
            dt = date_cols[0]
            hist[dt] = pd.to_datetime(hist[dt], errors="coerce")
            last_done = (
                hist.groupby(element_col)[dt].max().reset_index().rename(columns={dt: "last_maintenance_date"})
            )
            last_done["days_since_last"] = (TODAY - last_done["last_maintenance_date"]).dt.days
            missing = last_done[
                (last_done["last_maintenance_date"].isna()) | (last_done["days_since_last"] > 180)
            ]
            missing = missing.rename(columns={element_col: "Equipment Name"})

    # Replacement Prediction
    replacement = pd.DataFrame()
    if planned_df is not None and not planned_df.empty and element_col in planned_df.columns:
        date_cols = [c for c in planned_df.columns if "due" in c.lower()]
        if date_cols:
            due = date_cols[0]
            planned_df[due] = pd.to_datetime(planned_df[due], errors="coerce")
            planned_df["due_in_days"] = (planned_df[due] - TODAY).dt.days
            replacement = planned_df[
                (planned_df["due_in_days"] >= 0) & (planned_df["due_in_days"] <= 180)
            ][[element_col, due, "due_in_days"]]
            replacement = replacement.rename(columns={element_col: "Equipment Name"})

    # Purchase Prediction
    purchase = pd.DataFrame()
    if orders_df is not None and not orders_df.empty:
        oc = None
        for c in orders_df.columns:
            if "order" in c.lower() or "code" in c.lower():
                oc = c
                break
        if oc:
            orders_df[oc] = orders_df[oc].astype(str).str.strip()
            purchase = orders_df.groupby(oc).size().reset_index(name="order_count")
            purchase = purchase.rename(columns={oc: "Order Code"})

    return {
        "Missing Maintenance": missing,
        "Replacement Prediction": replacement,
        "Purchase Prediction": purchase,
    }


###############################################################################
# 🟦 ADVANCED INSIGHTS ENGINE (FULL FIXED VERSION)
###############################################################################
def _safe_days_between(dates):
    dates = pd.to_datetime(dates.dropna()).sort_values()
    if len(dates) < 2:
        return np.nan
    return dates.diff().dt.days.dropna().mean()


def generate_advanced_insights(loaded_files: dict, element_name_col: str = "Element Name"):

    # FIRST generate practical insights
    base = analyze_practical_insights(loaded_files, element_name_col)

    histories = []
    for name, df in loaded_files.items():
        if "history" in name.lower():
            histories.append(_try_date_parse(df))

    hist = pd.concat(histories, ignore_index=True, sort=False) if histories else pd.DataFrame()

    # Detect equipment column
    element_col = None
    for c in hist.columns:
        if element_name_col.lower() in c.lower():
            element_col = c
            break

    if element_col is None and not hist.empty:
        element_col = hist.columns[0]

    # ----------------------------
    # BUILD KPIs (ALWAYS SAFE)
    # ----------------------------
    kpi_rows = []
    if not hist.empty and element_col in hist.columns:

        # detect ANY date column
        date_cols = [
            c for c in hist.columns if "date" in c.lower() or "done" in c.lower() or "maintenance" in c.lower()
        ]

        dtcol = date_cols[0] if date_cols else None

        if dtcol:
            hist[dtcol] = pd.to_datetime(hist[dtcol], errors="coerce")

        for name, g in hist.groupby(element_col):
            if dtcol:
                last = g[dtcol].max()
                mean_int = _safe_days_between(g[dtcol])
                days_since = (pd.Timestamp.now() - last).days if pd.notna(last) else np.nan
            else:
                last, mean_int, days_since = pd.NaT, np.nan, np.nan

            kpi_rows.append({
                "Equipment Name": name,
                "events": len(g),
                "last_event_date": last,
                "days_since_last": days_since,
                "mean_interval_days": mean_int,
            })

    kpis = pd.DataFrame(kpi_rows)

    # ----------------------------
    # BUILD RISK TABLE (SAFE)
    # ----------------------------
    risk_rows = []
    for _, r in kpis.iterrows():
        score = 0
        if pd.notna(r["days_since_last"]) and r["days_since_last"] > 365:
            score += 40
        if pd.notna(r["mean_interval_days"]) and r["mean_interval_days"] < 30:
            score += 30
        if r["events"] > 10:
            score += 15

        risk_rows.append({
            "Equipment Name": r["Equipment Name"],
            "risk_score": min(score, 100)
        })

    risk_table = pd.DataFrame(risk_rows)

    # prevent crash
    if "risk_score" in risk_table.columns:
        risk_table = risk_table.sort_values("risk_score", ascending=False)
    else:
        risk_table = pd.DataFrame(columns=["Equipment Name", "risk_score"])

    # ----------------------------
    # BUILD SMART SUMMARY
    # ----------------------------
    summary_text = f"""
SMART SUMMARY
-------------
Total Equipment Analyzed: {len(kpis)}

Average Risk Score: {risk_table['risk_score'].mean() if not risk_table.empty else 0:.1f}

Top High-Risk Equipment:
{risk_table.head(5).to_string(index=False) if not risk_table.empty else "No risk data available."}

"""

    # return complete bundle
    return {
        "kpis": kpis,
        "risk_table": risk_table,
        "summary_text": summary_text,
        "base_insights": base,
    }

# core/analyzer.py
import pandas as pd
import numpy as np
from datetime import timedelta

# Helper: try to parse date-like columns
def _try_date_parse(df):
    df = df.copy()
    for c in df.columns:
        cl = str(c).lower()
        if "date" in cl or cl in ("last","due","done"):
            df[c] = pd.to_datetime(df[c], errors="coerce", dayfirst=True)
    # extra pass
    for c in df.columns:
        if "done" in str(c).lower() and "date" in str(c).lower():
            df[c] = pd.to_datetime(df[c], errors="coerce", dayfirst=True)
    return df


def analyze_practical_insights(loaded_files: dict, element_name_col: str = "Element Name"):
    """
    Accepts loaded_files: dict(name -> DataFrame)
    Returns dict with three DataFrames (Missing Maintenance, Replacement Prediction, Purchase Prediction).
    Each result tries to include a 'reference' column that points to source file and row where the data came from.
    """
    histories = []
    planned_df = None
    orders_df = None
    history_sources = []

    # identify files heuristically
    for name, df in loaded_files.items():
        lname = name.lower()
        if "maintenance history" in lname or "history" in lname:
            df2 = _try_date_parse(df)
            df2["_source_file"] = name
            histories.append(df2)
        elif "planned" in lname or "maintenance planned" in lname or "maintenance_plan" in lname:
            planned_df = _try_date_parse(df).copy()
            planned_df["_source_file"] = name
        elif "order" in lname:
            orders_df = df.copy()
            orders_df["_source_file"] = name

    if histories:
        hist = pd.concat(histories, ignore_index=True, sort=False)
    else:
        hist = pd.DataFrame()

    # normalize column names
    def clean_cols(df):
        df = df.copy()
        df.columns = [str(c).strip().replace("\n", " ").replace("\r", " ") for c in df.columns]
        return df
    hist = clean_cols(hist)
    if planned_df is not None:
        planned_df = clean_cols(planned_df)
    if orders_df is not None:
        orders_df = clean_cols(orders_df)

    # detect element/equipment column
    def find_element_column(df):
        if df is None or df.empty:
            return None
        cols = [str(c) for c in df.columns]
        if element_name_col in cols:
            return element_name_col
        for c in cols:
            cl = c.lower()
            if "element" in cl or "equipment" in cl or "element name" in cl:
                return c
        return cols[0] if cols else None

    element_col = find_element_column(hist if not hist.empty else planned_df)

    # find done column
    done_col = None
    for c in hist.columns:
        cl = c.lower()
        if "done" in cl and "date" in cl:
            done_col = c
            break
    if done_col is None:
        for c in hist.columns:
            try:
                if pd.api.types.is_datetime64_any_dtype(hist[c]):
                    done_col = c
                    break
            except Exception:
                pass

    # find due column in planned
    due_col = None
    if planned_df is not None:
        for c in planned_df.columns:
            cl = c.lower()
            if "due" in cl and ("date" in cl or "due" == cl.strip()):
                due_col = c
                break
        if due_col is None:
            for c in planned_df.columns:
                try:
                    if pd.api.types.is_datetime64_any_dtype(planned_df[c]):
                        due_col = c
                        break
                except Exception:
                    pass

    # Build last maintenance per element from histories
    last_done = pd.DataFrame(columns=[element_col, "last_maintenance_date", "_source_file", "_source_row"]) if element_col else pd.DataFrame()
    if done_col and element_col and not hist.empty:
        hist_subset = hist[[element_col, done_col, "_source_file"]].copy()
        hist_subset[done_col] = pd.to_datetime(hist_subset[done_col], errors="coerce")
        # keep row index as reference
        hist_subset["_row_index"] = hist_subset.index
        last = hist_subset.sort_values(by=[element_col, done_col]).groupby(element_col).last().reset_index()
        last_done = last.rename(columns={done_col: "last_maintenance_date", "_source_file": "_source_file", "_row_index": "_source_row"})[ [element_col, "last_maintenance_date", "_source_file", "_source_row"] ]
    else:
        last_done = pd.DataFrame(columns=[element_col, "last_maintenance_date", "_source_file", "_source_row"])

    # Merge planned
    merged = last_done.copy()
    if planned_df is not None and element_col in planned_df.columns:
        pl_cols = [c for c in planned_df.columns if str(c).lower() in ("last","due","last maintenance","due date","last date")]
        # keep a single row per element from planned
        pl_small = planned_df[[element_col] + [c for c in pl_cols if c in planned_df.columns]].drop_duplicates(subset=[element_col])
        pl_small = pl_small.rename(columns={c: c for c in pl_small.columns})
        merged = pd.merge(merged, pl_small, on=element_col, how="outer")

    # fallback last_maintenance_date from Last column if exists
    if "Last" in merged.columns:
        merged["last_maintenance_date"] = pd.to_datetime(merged.get("last_maintenance_date"), errors="coerce").combine_first(pd.to_datetime(merged["Last"], errors="coerce"))
    else:
        merged["last_maintenance_date"] = pd.to_datetime(merged.get("last_maintenance_date"), errors="coerce")

    TODAY = pd.Timestamp.now()
    merged["days_since_last"] = (TODAY - merged["last_maintenance_date"]).dt.days

    # Missing maintenance
    missing = merged[(merged["last_maintenance_date"].isna()) | (merged["days_since_last"] > 180)].copy()
    if element_col in missing.columns:
        missing = missing.rename(columns={element_col: "Equipment Name"})
    missing = missing.sort_values(by="days_since_last", ascending=False)

    # Replacement prediction: due within 180 days
    replacement = pd.DataFrame()
    if planned_df is not None and due_col and element_col in planned_df.columns:
        planned_copy = planned_df[[element_col, due_col]].copy()
        planned_copy[due_col] = pd.to_datetime(planned_copy[due_col], errors="coerce")
        planned_copy["due_in_days"] = (planned_copy[due_col] - TODAY).dt.days
        replacement = planned_copy[(planned_copy["due_in_days"].notna()) & (planned_copy["due_in_days"] >= 0) & (planned_copy["due_in_days"] <= 180)]
        replacement = replacement.rename(columns={element_col: "Equipment Name", due_col: "Due"})

    # Purchase prediction: top order codes
    purchase = pd.DataFrame()
    if orders_df is not None and not orders_df.empty:
        oc = None
        for c in orders_df.columns:
            if "order" in c.lower() and "code" in c.lower():
                oc = c
                break
        if oc is None:
            for c in orders_df.columns:
                if "order" in c.lower() or "code" in c.lower():
                    oc = c
                    break
        if oc is not None:
            orders_df[oc] = orders_df[oc].astype(str).str.strip()
            purchase = orders_df.groupby(oc).size().reset_index(name="order_count").sort_values("order_count", ascending=False)
            purchase = purchase.rename(columns={oc: "Order Code"})

    # Ensure shapes
    if missing.empty:
        missing = pd.DataFrame(columns=["Equipment Name", "last_maintenance_date", "days_since_last", "_source_file", "_source_row"])
    if replacement.empty:
        replacement = pd.DataFrame(columns=["Equipment Name", "Due", "due_in_days"])
    if purchase.empty:
        purchase = pd.DataFrame(columns=["Order Code", "order_count"])

    return {
        "Missing Maintenance": missing[["Equipment Name", "last_maintenance_date", "days_since_last", "_source_file", "_source_row"]] if "Equipment Name" in missing.columns else missing,
        "Replacement Prediction": replacement[["Equipment Name", "Due", "due_in_days"]] if "Equipment Name" in replacement.columns else replacement,
        "Purchase Prediction": purchase
    }


def generate_advanced_insights(loaded_files: dict, element_name_col: str = "Element Name"):
    """
    Produce advanced insights: summary_text, kpis DataFrame, risk_table DataFrame.
    risk_table has a 'risk_score' column (higher = more urgent).
    Also return references when possible.
    """
    # Reuse analyze_practical_insights to get replacement/missing/purchase
    practical = analyze_practical_insights(loaded_files, element_name_col=element_name_col)

    # KPIs (derived)
    kpis = []
    # equipment count (from merged files heuristically)
    equipment_names = set()
    for df in loaded_files.values():
        if df is None:
            continue
        for c in df.columns:
            if element_name_col in df.columns:
                equipment_names.update(df[element_name_col].dropna().astype(str).unique())
                break
    total_equipment = len(equipment_names)
    kpis.append({"metric": "Total Equipment (unique names found)", "value": total_equipment})

    # missing count
    missing_df = practical.get("Missing Maintenance", pd.DataFrame())
    missing_count = 0 if missing_df.empty else len(missing_df)
    kpis.append({"metric": "Equipment missing maintenance (>180 days or never)", "value": missing_count})

    # upcoming replacements
    replacement_df = practical.get("Replacement Prediction", pd.DataFrame())
    upcoming_replacements = 0 if replacement_df.empty else len(replacement_df)
    kpis.append({"metric": "Planned replacements in next 180 days", "value": upcoming_replacements})

    # purchase top items
    purchase_df = practical.get("Purchase Prediction", pd.DataFrame())
    top_orders = [] if purchase_df.empty else purchase_df.head(5).to_dict(orient="records")

    kpi_df = pd.DataFrame(kpis)

    # Risk ranking: combine missing and replacement into risk rows with score
    risk_rows = []
    # missing equipment -> high risk
    if not missing_df.empty:
        for idx, row in missing_df.reset_index(drop=True).iterrows():
            equip = row.get("Equipment Name", "<unknown>")
            days = row.get("days_since_last", np.nan)
            # score: missing -> base 80 + normalized by days
            score = 80.0
            if pd.notna(days):
                score += min(20.0, days / 30.0)  # each month adds some risk (capped)
            ref = {"type": "table", "name": row.get("_source_file"), "location": f"row:{int(row.get('_source_row'))+1 if pd.notna(row.get('_source_row')) else 'unknown'}"}
            reason = "Missing maintenance (>180 days or never recorded)"
            risk_rows.append({"equipment": equip, "risk_score": round(float(score), 2), "reason": reason, "reference": ref})

    # replacements close -> medium risk scaled by due_in_days
    if not replacement_df.empty:
        for idx, row in replacement_df.reset_index(drop=True).iterrows():
            equip = row.get("Equipment Name", "<unknown>")
            due_days = row.get("due_in_days", np.nan)
            if pd.isna(due_days):
                continue
            # closer due date -> higher score
            score = max(0.0, 70.0 - float(due_days) / 3.0)  # within 0 -> 70, farther reduces
            ref = {"type": "table", "name": getattr(row, "_source_file", "planned"), "location": f"due_in_days:{due_days}"}
            reason = f"Planned due in {int(due_days)} days"
            risk_rows.append({"equipment": equip, "risk_score": round(float(score), 2), "reason": reason, "reference": ref})

    # if nothing found, return empty
    if not risk_rows:
        risk_table = pd.DataFrame(columns=["equipment", "risk_score", "reason", "reference"])
    else:
        risk_table = pd.DataFrame(risk_rows).sort_values("risk_score", ascending=False)

    # Build summary_text
    summary_lines = []
    summary_lines.append(f"Total equipment detected: {total_equipment}")
    summary_lines.append(f"Missing maintenance (>180d or never): {missing_count}")
    summary_lines.append(f"Planned replacements within 180 days: {upcoming_replacements}")
    summary_lines.append(f"Top purchase order codes (sample): {top_orders if top_orders else 'N/A'}")
    summary_text = "\n".join(summary_lines)

    return {
        "summary_text": summary_text,
        "kpis": kpi_df,
        "risk_table": risk_table
    }

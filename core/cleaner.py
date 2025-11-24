# core/cleaner.py
import pandas as pd

def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Safe cleaning:
    - copy to avoid chained-assignment warnings
    - normalize column names (strip)
    - convert any date-like columns safely
    - fill numeric NaNs with median (or 0 if empty)
    - fill object NaNs with empty string
    """
    if df is None:
        return df
    df = df.copy()  # avoids SettingWithCopyWarning

    # Normalize column names (trim only; we keep original text to match keywords later)
    df.columns = [str(c).strip() for c in df.columns]

    # Try convert obvious date-like columns (heuristic: column name contains 'date' or 'time' or 'created' or 'service')
    for col in df.columns:
        col_l = col.lower()
        if any(k in col_l for k in ("date", "time", "created", "service", "serviced", "planned")):
            try:
                converted = pd.to_datetime(df[col], errors="coerce")
                df.loc[:, col] = converted
            except Exception:
                # leave as-is if conversion fails
                pass

    # Numeric columns: fill NaN with median or 0
    for col in df.columns:
        try:
            if pd.api.types.is_numeric_dtype(df[col]):
                if df[col].notna().sum() == 0:
                    df.loc[:, col] = df[col].fillna(0)
                else:
                    median_val = df[col].median()
                    df.loc[:, col] = df[col].fillna(median_val)
        except Exception:
            continue

    # Object/text columns: fill with empty string
    for col in df.select_dtypes(include=["object"]).columns:
        df.loc[:, col] = df[col].fillna("")

    # Drop exact duplicate rows
    df = df.drop_duplicates(ignore_index=True)

    return df

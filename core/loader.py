# core/loader.py
import os
import pandas as pd
from typing import List

EXCEL_EXT = (".xlsx", ".xls", ".csv")

def _read_file(path: str) -> pd.DataFrame:
    if path.lower().endswith(".csv"):
        return pd.read_csv(path)
    return pd.read_excel(path)

def list_data_files(folder: str) -> List[str]:
    if not os.path.exists(folder):
        return []
    files = [os.path.join(folder, f) for f in os.listdir(folder)
             if f.lower().endswith(EXCEL_EXT) and not f.startswith("~$")]
    return files

def load_all_excels(folder_path: str) -> pd.DataFrame:
    """
    Loads all excel/csv files in folder_path and concatenates them into one frame.
    Keeps a source_file column for tracing.
    Returns empty DataFrame if no files.
    """
    files = list_data_files(folder_path)
    frames = []
    for f in files:
        try:
            df = _read_file(f)
            if df is None:
                continue
            # Ensure columns are strings
            df.columns = [str(c) for c in df.columns]
            df = df.copy()
            df["source_file"] = os.path.basename(f)
            frames.append(df)
            print(f"Loaded {os.path.basename(f)} => {df.shape[0]} rows, {df.shape[1]} cols")
        except Exception as e:
            print(f"Failed to load {f}: {e}")
    if not frames:
        return pd.DataFrame()
    merged = pd.concat(frames, ignore_index=True, sort=False)
    return merged

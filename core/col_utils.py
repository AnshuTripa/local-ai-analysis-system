# core/col_utils.py
from typing import List, Optional

def find_column_by_keywords(columns: List[str], keywords: List[str]) -> Optional[str]:
    """
    Return the first column name from `columns` that contains any of the keywords (case-insensitive).
    Order of keywords is priority.
    """
    cols_lower = [c.lower() for c in columns]
    for kw in keywords:
        kw = kw.lower()
        for i, c in enumerate(cols_lower):
            if kw in c:
                return columns[i]
    return None

# core/learning_table.py
import csv
import os

LEARNING_TABLE = "learning_table.csv"

def load_learning_terms():
    """
    Loads the CSV learning_table.csv from project root.
    Returns dict: {term: definition}
    """
    if not os.path.exists(LEARNING_TABLE):
        return {}

    terms = {}
    with open(LEARNING_TABLE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            term = (row.get("term") or "").strip()
            definition = (row.get("definition") or "").strip()
            if term and definition:
                terms[term] = definition
    return terms

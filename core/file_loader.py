# core/file_loader.py
import os
import pandas as pd
from PyPDF2 import PdfReader
import docx

from core.cleaning_tracker import is_already_cleaned, mark_cleaned

# simple in-memory cache for extracted document text (path -> text)
_document_cache = {}

def _read_excel_fast(path):
    # use openpyxl engine for xlsx for speed & stability
    return pd.read_excel(path, engine="openpyxl")

def _read_csv_fast(path):
    return pd.read_csv(path, low_memory=False)


def load_folder_files(folder_path):
    tables = {}
    documents = {}
    msg = ""

    if not os.path.exists(folder_path):
        return tables, documents, "Folder not found."

    for fname in os.listdir(folder_path):
        fpath = os.path.join(folder_path, fname)
        lname = fname.lower()

        # --- Excel / CSV ---
        if lname.endswith((".xlsx", ".xls", ".csv")):

            # Skip if filename suggests already cleaned
            if any(key in lname for key in ["clean", "cleaned", "processed", "final"]):
                print(f"Skipping file (name suggests cleaned): {fname}")
                try:
                    if lname.endswith(".csv"):
                        tables[fname] = _read_csv_fast(fpath)
                    else:
                        tables[fname] = _read_excel_fast(fpath)
                except Exception as e:
                    print(f"Error loading cleaned file {fname}: {e}")
                continue

            # Skip if hash suggests file already cleaned before
            if is_already_cleaned(fpath):
                print(f"Skipping cleaning (hash match): {fname}")
                try:
                    if lname.endswith(".csv"):
                        tables[fname] = _read_csv_fast(fpath)
                    else:
                        tables[fname] = _read_excel_fast(fpath)
                except Exception as e:
                    print(f"Error loading file {fname}: {e}")
                continue

            # Otherwise, clean the file
            print(f"Cleaning file: {fname}")
            try:
                if lname.endswith(".csv"):
                    df = _read_csv_fast(fpath)
                else:
                    df = _read_excel_fast(fpath)

                # Minimal cleaning (fast): trim column names, drop fully-empty columns
                df.columns = [str(c).strip().replace("\n", " ") for c in df.columns]
                # drop columns that are entirely NaN to reduce memory
                non_empty_cols = [c for c in df.columns if not df[c].isna().all()]
                df = df[non_empty_cols]

                tables[fname] = df
                # mark file as cleaned (one-time)
                mark_cleaned(fpath)

            except Exception as e:
                print(f"Error cleaning {fname}: {e}")

        # --- PDF ---
        elif lname.endswith(".pdf"):
            try:
                if fpath in _document_cache:
                    documents[fname] = _document_cache[fpath]
                    continue

                reader = PdfReader(fpath)
                pages = [page.extract_text() for page in reader.pages]
                text = "\n".join([p for p in pages if p])
                documents[fname] = text
                _document_cache[fpath] = text
            except Exception as e:
                print(f"Error reading PDF {fname}: {e}")
                documents[fname] = ""

        # --- DOCX ---
        elif lname.endswith(".docx"):
            try:
                if fpath in _document_cache:
                    documents[fname] = _document_cache[fpath]
                    continue

                doc = docx.Document(fpath)
                text = "\n".join([p.text for p in doc.paragraphs if p.text])
                documents[fname] = text
                _document_cache[fpath] = text
            except Exception as e:
                print(f"Error reading DOCX {fname}: {e}")
                documents[fname] = ""

        # --- TXT ---
        elif lname.endswith(".txt"):
            try:
                if fpath in _document_cache:
                    documents[fname] = _document_cache[fpath]
                    continue

                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    text = f.read()
                documents[fname] = text
                _document_cache[fpath] = text
            except Exception as e:
                print(f"Error reading TXT {fname}: {e}")
                documents[fname] = ""

    return tables, documents, "Loaded"

# core/file_loader.py
import os
import io
from typing import Tuple, Dict
import pandas as pd

# PDF & DOCX libs (optional)
try:
    import PyPDF2
except Exception:
    PyPDF2 = None
try:
    import docx
except Exception:
    docx = None


def _is_temp_file(fname: str) -> bool:
    """Skip Office temp files that start with ~$ or similar."""
    base = os.path.basename(fname)
    return base.startswith("~$") or base.endswith(".tmp")


def _read_excel(path: str):
    try:
        return pd.read_excel(path, engine="openpyxl")
    except Exception:
        # fallback to default engine
        return pd.read_excel(path)


def _read_csv(path: str):
    return pd.read_csv(path)


def _extract_text_from_pdf(path: str) -> str:
    if PyPDF2 is None:
        raise ImportError("PyPDF2 not installed. Install with: pip install PyPDF2")
    text = []
    try:
        with open(path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for pageno, page in enumerate(reader.pages):
                try:
                    pg_text = page.extract_text() or ""
                except Exception:
                    pg_text = ""
                if pg_text:
                    # mark page header for reference
                    text.append(f"[PAGE {pageno+1}]\n{pg_text}")
    except Exception as e:
        # graceful error
        return f"[ERROR reading PDF: {e}]"
    return "\n\n".join(text)


def _extract_text_from_docx(path: str) -> str:
    if docx is None:
        raise ImportError("python-docx not installed. Install with: pip install python-docx")
    try:
        d = docx.Document(path)
        paragraphs = [p.text for p in d.paragraphs if p.text and p.text.strip()]
        return "\n".join(paragraphs)
    except Exception as e:
        return f"[ERROR reading DOCX: {e}]"


def _read_txt(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception:
        with open(path, "r", encoding="latin-1", errors="ignore") as f:
            return f.read()


def load_folder_files(folder_path: str) -> Tuple[Dict[str, pd.DataFrame], Dict[str, str], str]:
    """
    Scans folder_path and returns:
      - tables: dict of filename -> pandas.DataFrame (xlsx/xls/csv)
      - documents: dict of filename -> extracted text (pdf/docx/txt)
      - message: str with processing summary and warning messages
    Skips temp files (e.g., starting with ~$).
    """
    tables = {}
    documents = {}
    msgs = []

    if not folder_path:
        return tables, documents, "No folder provided."

    if not os.path.isdir(folder_path):
        return tables, documents, f"Folder not found: {folder_path}"

    for entry in os.listdir(folder_path):
        fpath = os.path.join(folder_path, entry)
        if not os.path.isfile(fpath):
            continue
        if _is_temp_file(entry):
            msgs.append(f"Skipping temp file: {entry}")
            continue

        lower = entry.lower()
        try:
            if lower.endswith((".xlsx", ".xls")):
                try:
                    df = _read_excel(fpath)
                    tables[entry] = df
                    msgs.append(f"Loaded Excel: {entry}")
                except Exception as e:
                    msgs.append(f"Error loading Excel {entry}: {e}")
            elif lower.endswith(".csv"):
                try:
                    df = _read_csv(fpath)
                    tables[entry] = df
                    msgs.append(f"Loaded CSV: {entry}")
                except Exception as e:
                    msgs.append(f"Error loading CSV {entry}: {e}")
            elif lower.endswith(".pdf"):
                try:
                    text = _extract_text_from_pdf(fpath)
                    documents[entry] = text
                    msgs.append(f"Loaded PDF: {entry}")
                except Exception as e:
                    msgs.append(f"Error reading PDF {entry}: {e}")
            elif lower.endswith(".docx"):
                try:
                    text = _extract_text_from_docx(fpath)
                    documents[entry] = text
                    msgs.append(f"Loaded DOCX: {entry}")
                except Exception as e:
                    msgs.append(f"Error reading DOCX {entry}: {e}")
            elif lower.endswith(".txt"):
                try:
                    text = _read_txt(fpath)
                    documents[entry] = text
                    msgs.append(f"Loaded TXT: {entry}")
                except Exception as e:
                    msgs.append(f"Error reading TXT {entry}: {e}")
            else:
                msgs.append(f"Ignored file (unsupported): {entry}")
        except Exception as e:
            msgs.append(f"Unhandled error for {entry}: {e}")

    summary = "\n".join(msgs)
    return tables, documents, summary

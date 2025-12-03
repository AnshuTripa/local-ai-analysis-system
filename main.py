#!/usr/bin/env python3
"""
main.py - Updated central CLI for Local AI Analysis System
Keep this file in your project root and run with the project's venv active.
Compatible with: Python 3.12+, pandas 2.x
"""

import os
import re
import json
from datetime import datetime
from typing import Dict, Any, Optional, Tuple, List

import pandas as pd

# Core modules (present in repo)
from core.file_loader import load_folder_files  # returns (tables_dict, documents_dict, message)
from core.analyzer import analyze_practical_insights, generate_advanced_insights

# Defensive optional imports
try:
    from core.document_qa import extract_text_from_documents, chunk_and_index_documents, answer_from_doc_index
except Exception:
    extract_text_from_documents = None
    chunk_and_index_documents = None
    answer_from_doc_index = None

try:
    from core.llm_engine import ask_llm
except Exception:
    ask_llm = None

try:
    from core.cleaning_tracker import is_cleaned, mark_cleaned
    from core.cleaner import smart_clean_dataframe
except Exception:
    is_cleaned = None
    mark_cleaned = None
    smart_clean_dataframe = None

try:
    from core.learning_table import load_learning_table
except Exception:
    load_learning_table = None

DATA_FOLDER = "data"
OUTPUT_FOLDER = "output"

_last_ai_response: Optional[Dict[str, Any]] = None


# -------------------------
# Utilities
# -------------------------
def ensure_output_folder():
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)


def safe_print_df(df: pd.DataFrame, title: Optional[str] = None, max_rows: int = 20):
    if title:
        print("\n===== " + title + " =====")
    if df is None:
        print("(None)")
        return
    if isinstance(df, pd.DataFrame):
        if df.empty:
            print("(Empty)")
            return
        print(df.head(max_rows).to_string(index=False))
        if len(df) > max_rows:
            print(f"... ({len(df)} total rows)")
    else:
        print(str(df))


def export_df_to_excel(df: pd.DataFrame, path: str) -> Tuple[bool, Optional[str]]:
    try:
        df.to_excel(path, index=False)
        return True, None
    except Exception as e:
        return False, str(e)


def export_text_to_word(text: str, path: str) -> Tuple[bool, Optional[str]]:
    try:
        from docx import Document  # type: ignore
    except Exception:
        # fallback to plain text file
        try:
            with open(path.replace(".docx", ".txt"), "w", encoding="utf-8") as f:
                f.write(text)
            return True, None
        except Exception as e:
            return False, str(e)
    try:
        doc = Document()
        for line in text.splitlines():
            doc.add_paragraph(line)
        doc.save(path)
        return True, None
    except Exception as e:
        return False, str(e)


# -------------------------
# Load default tables from DATA_FOLDER
# -------------------------
def load_all_tables_from_datafolder() -> Dict[str, pd.DataFrame]:
    loaded: Dict[str, pd.DataFrame] = {}
    if not os.path.exists(DATA_FOLDER):
        print(f"Data folder '{DATA_FOLDER}' not found. Create it and put files there.")
        return loaded

    for fname in os.listdir(DATA_FOLDER):
        fpath = os.path.join(DATA_FOLDER, fname)
        if fname.lower().endswith((".xlsx", ".xls")):
            try:
                df = pd.read_excel(fpath)
                loaded[fname] = df
                print(f"Loaded Excel: {fname} ({len(df)} rows, {len(df.columns)} cols)")
            except Exception as e:
                print(f"Error loading {fname}: {e}")
        elif fname.lower().endswith(".csv"):
            try:
                df = pd.read_csv(fpath)
                loaded[fname] = df
                print(f"Loaded CSV: {fname} ({len(df)} rows, {len(df.columns)} cols)")
            except Exception as e:
                print(f"Error loading {fname}: {e}")
    return loaded


# -------------------------
# Document utilities: chunk long text into passages for indexing
# -------------------------
def chunk_text(text: str, chunk_size: int = 3000, overlap: int = 200) -> List[Dict[str, Any]]:
    """
    Returns list of dicts: [{'start': int,'end': int,'text': str, 'id': str}, ...]
    chunk_size in characters. Overlap characters to preserve context.
    """
    if not isinstance(text, str):
        text = str(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    n = len(text)
    chunks = []
    i = 0
    counter = 0
    while i < n:
        end = min(n, i + chunk_size)
        snippet = text[i:end]
        chunk_id = f"chunk_{counter}"
        chunks.append({"id": chunk_id, "start": i, "end": end, "text": snippet})
        counter += 1
        i = end - overlap if end < n else end
    return chunks


# -------------------------
# Simple content search across tables (pandas 2.x compatible)
# -------------------------
def find_in_tables(tables: Dict[str, pd.DataFrame], question: str, top_k: int = 8):
    q = str(question or "").strip().lower()
    if not q or not tables:
        return []

    tokens = [t for t in re.split(r"\W+", q) if t]
    if not tokens:
        return []

    matches = []
    for fname, df in tables.items():
        if df is None or df.empty:
            continue
        try:
            cols = list(df.columns)
        except Exception:
            continue

        for col in cols:
            try:
                series = df[col].astype(str).fillna("").str.strip()
            except Exception:
                try:
                    series = df[col].astype(str)
                except Exception:
                    continue

            # pandas 2.x uses .items()
            for idx, cell in series.items():
                if not isinstance(cell, str):
                    cell = str(cell)
                lc = cell.lower()
                hits = sum(1 for tok in tokens if tok in lc)
                if hits:
                    matches.append({
                        "file": fname,
                        "column": col,
                        "row_index": int(idx) if (isinstance(idx, (int, float)) or str(idx).isdigit()) else str(idx),
                        "snippet": cell[:800],
                        "hits": hits
                    })

    matches = sorted(matches, key=lambda x: x["hits"], reverse=True)
    return matches[:top_k]


# -------------------------
# Simple document search across extracted texts
# -------------------------
def find_in_documents(doc_index: Dict[str, str], question: str, top_k: int = 6):
    q = str(question or "").strip().lower()
    if not q or not doc_index:
        return []
    tokens = [t for t in re.split(r"\W+", q) if t]
    if not tokens:
        return []

    results = []
    for fname, text in doc_index.items():
        if not isinstance(text, str):
            continue
        lc = text.lower()
        hits = sum(1 for tok in tokens if tok in lc)
        if hits:
            # earliest position
            positions = [lc.find(tok) for tok in tokens if lc.find(tok) >= 0]
            pos = min(positions) if positions else -1
            if pos >= 0:
                start = max(0, pos - 200)
                snippet = text[start:start + 600].replace("\n", " ")
            else:
                snippet = text[:600].replace("\n", " ")
            results.append({"file": fname, "hits": hits, "snippet": snippet, "position": pos})
    results = sorted(results, key=lambda x: x["hits"], reverse=True)
    return results[:top_k]


# -------------------------
# Answering strictly from uploaded data
# -------------------------
def answer_using_data(question: str, tables: Dict[str, pd.DataFrame], doc_index: Dict[str, str]):
    if not question:
        return {"answer": "No question provided.", "table_refs": [], "doc_refs": []}

    table_refs = find_in_tables(tables, question, top_k=12)
    doc_refs = find_in_documents(doc_index, question, top_k=8)

    if table_refs:
        lines = []
        for tr in table_refs[:6]:
            lines.append(f"- Table '{tr['file']}', column '{tr['column']}', row {tr['row_index']}: {tr['snippet'][:200]}")
        answer_text = "Answer based on table data (references listed):\n\n" + "\n".join(lines)
    elif doc_refs:
        lines = []
        for dr in doc_refs[:6]:
            lines.append(f"- Document '{dr['file']}', approx position {dr['position']}: {dr['snippet'][:200]}")
        answer_text = "Answer based on document content (references listed):\n\n" + "\n".join(lines)
    else:
        answer_text = "No matching data found in the uploaded tables or documents for this question."

    return {"answer": answer_text, "table_refs": table_refs, "doc_refs": doc_refs}


# -------------------------
# Export last AI response helper
# -------------------------
def export_last_response(last_resp: Dict[str, Any], format_opt: int = 1):
    if not last_resp:
        print("No AI response available to export.")
        return

    ensure_output_folder()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    if format_opt == 1:
        rows = []
        for t in last_resp.get("table_refs", []):
            rows.append({"type": "table", **t})
        for d in last_resp.get("doc_refs", []):
            rows.append({"type": "doc", **d})
        df = pd.DataFrame(rows)
        out = os.path.join(OUTPUT_FOLDER, f"last_ai_response_{ts}.xlsx")
        ok, err = export_df_to_excel(df, out)
        if ok:
            print("Exported to:", out)
        else:
            print("Export error:", err)
    else:
        lines = []
        lines.append("AI Generated Response")
        lines.append("=" * 60)
        lines.append(f"Generated at: {datetime.now().isoformat()}")
        lines.append("")
        lines.append("Answer:")
        lines.append(last_resp.get("answer", ""))
        lines.append("")
        lines.append("Table references:")
        for tr in last_resp.get("table_refs", []):
            lines.append(json.dumps(tr, default=str))
        lines.append("")
        lines.append("Document references:")
        for dr in last_resp.get("doc_refs", []):
            lines.append(json.dumps(dr, default=str))

        report_text = "\n".join(lines)
        out_docx = os.path.join(OUTPUT_FOLDER, f"last_ai_response_{ts}.docx")
        ok, err = export_text_to_word(report_text, out_docx)
        if ok:
            print("Exported report to:", out_docx)
        else:
            out_txt = out_docx.replace(".docx", ".txt")
            with open(out_txt, "w", encoding="utf-8") as f:
                f.write(report_text)
            print("Exported fallback text report to:", out_txt)


# -------------------------
# Interactive menu loop
# -------------------------
def interactive_menu(tables: Dict[str, pd.DataFrame], documents: Dict[str, str], doc_index: Dict[str, str], learning_terms: Dict[str, str]):
    global _last_ai_response

    while True:
        print("\n-------- MENU --------")
        print("1. Practical Insights (Maintenance + Replacement + Purchase)")
        print("2. Ask a Question (Gemma LLM - Summary Mode) -- answers strictly from uploaded data")
        print("3. Exit")
        print("4. Preview Cleaned Data")
        print("5. Export Cleaned Files to Output Folder")
        print("6. Advanced Insights & Reasoning (Smart Summaries, Trends, Risks, Recommendations)")
        print("7. Folder-Based Analysis (Excel, CSV, PDF, Word, Text)")
        print("8. PDF & Word File Question-Answering")
        print("9. Export Last AI Response (Excel / Word / Report)")

        choice = input("Enter your choice: ").strip()

        # Option 1
        if choice == "1":
            print("Generating Practical Insights...")
            try:
                res = analyze_practical_insights(tables)
                if isinstance(res, dict):
                    for k, v in res.items():
                        safe_print_df(v, k)
                else:
                    print("Practical insights returned unexpected format:", type(res))
            except Exception as e:
                print("Error generating practical insights:", e)

        # Option 2
        elif choice == "2":
            q = input("Enter question (answers strictly from uploaded data): ").strip()
            ans_struct = answer_using_data(q, tables, doc_index)
            print("\n--- ANSWER (based on uploaded data) ---\n")
            print(ans_struct.get("answer", ""))
            _last_ai_response = ans_struct

            # Ask LLM to rephrase (still grounded)
            if ask_llm:
                use_llm = input("\nWould you like the LLM to generate a rephrased/explanatory answer using these references? (y/n): ").strip().lower()
                if use_llm == "y":
                    ctx = {
                        "table_refs": ans_struct.get("table_refs", [])[:12],
                        "doc_refs": ans_struct.get("doc_refs", [])[:8],
                        "learning_terms": learning_terms
                    }
                    try:
                        llm_ans = ask_llm(q, context=ctx, model_name="gemma:2b")
                        print("\n--- LLM Rephrased Answer ---\n")
                        print(llm_ans)
                        _last_ai_response = {"answer": llm_ans, "table_refs": ans_struct.get("table_refs", []), "doc_refs": ans_struct.get("doc_refs", [])}
                    except Exception as e:
                        print("LLM error:", e)

        # Option 3
        elif choice == "3":
            print("Exiting. Goodbye.")
            break

        # Option 4
        elif choice == "4":
            print("\nPreview original and cleaned (sample):")
            if not tables:
                print("- No table files loaded.")
            for name, df in tables.items():
                print(f"\n--- File: {name} (original sample) ---")
                safe_print_df(df.head(10))
                if smart_clean_dataframe:
                    try:
                        cleaned = smart_clean_dataframe(df.copy())
                        print(f"\n--- File: {name} (cleaned sample) ---")
                        safe_print_df(cleaned.head(10))
                    except Exception as e:
                        print("Cleaner preview failed:", e)
            if not documents:
                print("- No documents loaded.")
            for name, txt in documents.items():
                print(f"\n--- Document: {name} (first 800 chars) ---")
                print((txt or "")[:800])

        # Option 5
        elif choice == "5":
            ensure_output_folder()
            print("Exporting cleaned tables into output folder...")
            for fname, df in tables.items():
                if isinstance(df, pd.DataFrame):
                    outp = os.path.join(OUTPUT_FOLDER, f"cleaned_{fname}.xlsx")
                    try:
                        df.to_excel(outp, index=False)
                        print("Exported:", outp)
                    except Exception as e:
                        print("Export failed for", fname, "->", e)
            print("Exporting documents as text...")
            for dname, content in documents.items():
                safe_name = re.sub(r"[^\w\-_\. ]", "_", dname)
                outp = os.path.join(OUTPUT_FOLDER, f"doc_{safe_name}.txt")
                try:
                    with open(outp, "w", encoding="utf-8") as f:
                        f.write(content or "")
                    print("Exported:", outp)
                except Exception as e:
                    print("Write error:", e)
            print("Export complete.")

        # Option 6
        elif choice == "6":
            print("🧠 Generating Advanced Insights & Reasoning...")
            try:
                adv = generate_advanced_insights(tables, element_name_col="Element Name")
                print("\n=== SMART SUMMARY ===")
                print(adv.get("summary_text", "No summary found."))
                safe_print_df(adv.get("kpis"), "Equipment KPIs")
                safe_print_df(adv.get("risk_table"), "Risk Ranking Table (Highest Risk First)")
                _last_ai_response = {"answer": adv.get("summary_text", ""), "table_refs": adv.get("kpis", []), "doc_refs": []}
            except Exception as e:
                print("Advanced insights error:", e)

        # Option 7
        elif choice == "7":
            folder = input("Enter folder path for analysis: ").strip()
            if not folder:
                print("No folder provided.")
                continue
            print("Scanning folder...")
            try:
                tables2, docs2, msg = load_folder_files(folder)
            except Exception as e:
                print("Folder load error:", e)
                tables2, docs2, msg = {}, {}, str(e)

            print("\n=== TABLE FILES LOADED ===")
            for k in (tables2 or {}).keys():
                print(" -", k)
            print("\n=== DOCUMENT FILES LOADED ===")
            for k in (docs2 or {}).keys():
                print(" -", k)

            # One-time cleaning logic
            if tables2 and smart_clean_dataframe and is_cleaned and mark_cleaned:
                cleaned_tables = {}
                for fname, df in tables2.items():
                    try:
                        if is_cleaned(folder, fname):
                            cleaned_tables[fname] = df
                        else:
                            cleaned = smart_clean_dataframe(df)
                            cleaned_tables[fname] = cleaned
                            mark_cleaned(folder, fname)
                    except Exception:
                        cleaned_tables[fname] = df
                tables2 = cleaned_tables

            if tables2:
                try:
                    adv2 = generate_advanced_insights(tables2)
                    print("\nFolder-based SMART SUMMARY:")
                    print(adv2.get("summary_text", "No summary"))
                except Exception as e:
                    print("Advanced insights on folder error:", e)
            else:
                print("No table files found for advanced insights.")

            # Document extraction and indexing
            docs_texts = {}
            if docs2:
                if extract_text_from_documents:
                    try:
                        docs_texts = extract_text_from_documents(docs2)
                    except Exception as e:
                        print("Document extraction module failed:", e)
                        docs_texts = {k: (v if isinstance(v, str) else str(v)) for k, v in docs2.items()}
                else:
                    docs_texts = {k: (v if isinstance(v, str) else str(v)) for k, v in docs2.items()}

                # create chunk-level index for large docs
                for k, txt in list(docs_texts.items()):
                    if isinstance(txt, str) and len(txt) > 8000:
                        chunks = chunk_text(txt, chunk_size=4000, overlap=300)
                        # replace big text with joined id->text mapping (small)
                        docs_texts[k] = "\n\n".join([c["text"] for c in chunks])

                # If LLM available, produce a grounded summary
                combined_text = "\n\n".join(docs_texts.values())
                if ask_llm:
                    try:
                        print("\nSummarizing documents using LLM (grounded in extracted text)...")
                        summary = ask_llm("Summarize these documents and list top themes (base only on supplied text).", context={"docs": combined_text, "learning_terms": learning_terms}, model_name="gemma:2b")
                        print(summary)
                        _last_ai_response = {"answer": summary, "table_refs": [], "doc_refs": [{"file": k, "snippet": (v[:300] if v else "")} for k, v in docs_texts.items()][:10]}
                    except Exception as e:
                        print("LLM document summary error:", e)
                else:
                    print("LLM not available; document summarization skipped.")

            # merge folder results into workspace
            tables.update(tables2 or {})
            documents.update(docs2 or {})
            doc_index.update(docs_texts or {})

        # Option 8
        elif choice == "8":
            folder = input("Enter folder path containing PDF/DOCX files (or press Enter to use previously loaded docs): ").strip()
            local_docs = {}
            if folder:
                try:
                    _, docs2, _ = load_folder_files(folder)
                    if extract_text_from_documents:
                        try:
                            local_docs = extract_text_from_documents(docs2)
                        except Exception:
                            local_docs = {k: (v if isinstance(v, str) else str(v)) for k, v in docs2.items()}
                    else:
                        local_docs = {k: (v if isinstance(v, str) else str(v)) for k, v in docs2.items()}
                except Exception as e:
                    print("Folder load error:", e)
                    continue
            else:
                local_docs = doc_index

            if not local_docs:
                print("No documents available to answer from.")
                continue

            q = input("Ask a question based on the documents (answers strictly from extracted content): ").strip()
            if not q:
                print("No question provided.")
                continue

            # If advanced doc QA available, use it
            if answer_from_doc_index and chunk_and_index_documents:
                try:
                    index = chunk_and_index_documents(local_docs)
                    doc_answer = answer_from_doc_index(q, index, top_k=6)
                    print("\n--- DOCUMENT-BASED ANSWER (from doc index) ---\n")
                    print(doc_answer.get("answer", ""))
                    _last_ai_response = {"answer": doc_answer.get("answer", ""), "table_refs": [], "doc_refs": doc_answer.get("references", [])}
                    continue
                except Exception as e:
                    print("Document QA module error:", e)

            # Fallback simple search
            doc_refs = find_in_documents(local_docs, q, top_k=10)
            if doc_refs:
                print("\n--- DOCUMENT-BASED ANSWER (references) ---\n")
                for dr in doc_refs[:10]:
                    print(f"File: {dr['file']}  (hits: {dr['hits']})")
                    print("Snippet:", dr['snippet'])
                    print("-" * 70)
                _last_ai_response = {"answer": "Answer based on document snippets (see references).", "table_refs": [], "doc_refs": doc_refs}
            else:
                print("No matching content found in available documents.")

        # Option 9
        elif choice == "9":
            if _last_ai_response is None:
                print("No AI response available to export.")
                continue
            print("Choose export format:")
            print("1. Excel")
            print("2. Word Document")
            print("3. Clean Tabulated Word Report")
            opt = input("Enter option: ").strip()
            try:
                fmt = int(opt)
            except Exception:
                print("Invalid option.")
                continue
            export_last_response(_last_ai_response, format_opt=fmt)

        else:
            print("Invalid choice. Try again.")


# -------------------------
# main()
# -------------------------
def main():
    print("Loading table files from default data folder...")
    tables = load_all_tables_from_datafolder()

    documents: Dict[str, str] = {}
    doc_index: Dict[str, str] = {}
    learning_terms: Dict[str, str] = {}

    # Load learning table if present
    if load_learning_table:
        try:
            learning_terms = load_learning_table()
            print(f"Loaded learning table with {len(learning_terms)} entries.")
        except Exception as e:
            print("Learning table load error:", e)

    # Try to extract docs from data folder too
    try:
        folder_tables, folder_docs, msg = load_folder_files(DATA_FOLDER)
        if isinstance(folder_tables, dict):
            for k, v in folder_tables.items():
                if k not in tables:
                    tables[k] = v
        if isinstance(folder_docs, dict):
            for k, v in folder_docs.items():
                documents[k] = v if isinstance(v, str) else str(v)
                doc_index[k] = documents[k]
    except Exception:
        # non-fatal
        pass

    # Precompute advanced insights (best-effort)
    try:
        _ = generate_advanced_insights(tables)
    except Exception:
        pass

    interactive_menu(tables, documents, doc_index, learning_terms)


if __name__ == "__main__":
    main()

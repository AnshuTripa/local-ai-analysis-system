# main.py
import os
import pandas as pd
from core.analyzer import analyze_practical_insights, generate_advanced_insights
from core.llm_engine import ask_llm
from core.file_loader import load_folder_files

# NEW IMPORT for Export Feature
from core.document_export import (
    export_to_excel,
    export_to_word,
    export_tabulated_report,
)

# NEW IMPORT for Document Question-Answering
from core.document_qa import extract_documents_from_folder

DATA_FOLDER = "data"
OUTPUT_FOLDER = "output"

# Global variable to store last AI response
last_answer = ""


def load_all_files():
    loaded = {}
    if not os.path.exists(DATA_FOLDER):
        print(f"Data folder '{DATA_FOLDER}' not found!")
        return loaded

    for fname in os.listdir(DATA_FOLDER):
        fpath = os.path.join(DATA_FOLDER, fname)

        try:
            if fname.lower().endswith((".xlsx", ".xls")):
                loaded[fname] = pd.read_excel(fpath)
                print(f"Loaded Excel: {fname}")
            elif fname.lower().endswith(".csv"):
                loaded[fname] = pd.read_csv(fpath)
                print(f"Loaded CSV: {fname}")
        except Exception as e:
            print(f"Error loading {fname}: {e}")

    return loaded


def pretty_print_df(df, title=None, max_rows=20):
    if title:
        print("\n===== " + title + " =====")
    if df is None or df.empty:
        print("(Empty)")
        return
    print(df.head(max_rows).to_string(index=False))
    if len(df) > max_rows:
        print(f"... ({len(df)} total rows)")


def export_frames(frames: dict, folder=OUTPUT_FOLDER):
    os.makedirs(folder, exist_ok=True)
    for key, df in frames.items():
        outfile = os.path.join(folder, f"{key.replace(' ', '_').lower()}.xlsx")
        try:
            df.to_excel(outfile, index=False)
            print(f"Exported: {outfile}")
        except Exception as e:
            print(f"Error exporting {key}: {e}")


def main():
    global last_answer

    print("Loading data files...")
    loaded = load_all_files()

    while True:
        print("\n-------- MENU --------")
        print("1. Practical Insights (Maintenance + Replacement + Purchase)")
        print("2. Ask a Question (Gemma LLM - Summary Mode)")
        print("3. Exit")
        print("4. Preview Cleaned Data")
        print("5. Export Cleaned Files to Output Folder")
        print("6. Advanced Insights & Reasoning (Smart Summaries, Trends, Risks, Recommendations)")
        print("7. Folder-Based Analysis (Excel, CSV, PDF, Word, Text)")
        print("8. PDF & Word File Question-Answering")  # NEW FEATURE
        print("9. Export Last AI Response (Excel / Word / Report)")  # NEW FEATURE

        choice = input("Enter your choice: ").strip()

        # -------------------------------------------
        # OPTION 1 – Practical Insights
        # -------------------------------------------
        if choice == "1":
            print("Generating Practical Insights...")
            results = analyze_practical_insights(loaded)
            for key, df in results.items():
                pretty_print_df(df, key)

        # -------------------------------------------
        # OPTION 2 – Ask Question
        # -------------------------------------------
        elif choice == "2":
            q = input("Enter your question for Gemma: ").strip()
            ctx = {"files_loaded": list(loaded.keys())}
            ans = ask_llm(q, context=ctx, model_name="gemma:2b")

            last_answer = ans
            print("\n--- Gemma Response ---\n")
            print(ans)

        # -------------------------------------------
        # OPTION 3 – Exit
        # -------------------------------------------
        elif choice == "3":
            print("Thank you!")
            break

        # -------------------------------------------
        # OPTION 4 – Preview Loaded Files
        # -------------------------------------------
        elif choice == "4":
            for name, df in loaded.items():
                pretty_print_df(df, f"File: {name}")

        # -------------------------------------------
        # OPTION 5 – Export Cleaned Data Files
        # -------------------------------------------
        elif choice == "5":
            export_frames(loaded)

        # -------------------------------------------
        # OPTION 6 – Advanced Insights
        # -------------------------------------------
        elif choice == "6":
            print("🧠 Generating Advanced Insights & Reasoning...")
            adv = generate_advanced_insights(loaded, element_name_col="Element Name")

            print("\n=== SMART SUMMARY ===")
            print(adv["summary_text"])

            pretty_print_df(adv["kpis"], "Equipment KPIs")
            pretty_print_df(adv["risk_table"], "Risk Ranking Table")

            last_answer = adv["summary_text"]

        # -------------------------------------------
        # OPTION 7 – Folder-Based Analysis
        # -------------------------------------------
        elif choice == "7":
            folder = input("Enter folder path for analysis: ").strip()

            print("Scanning folder...")
            tables, documents, msg = load_folder_files(folder)

            # Print table files
            print("\n=== TABLE FILES LOADED ===")
            for k in tables:
                print(" -", k)

            # Print document files
            print("\n=== DOCUMENT FILES LOADED ===")
            for k in documents:
                print(" -", k)

            # Advanced insights for tables
            if tables:
                adv = generate_advanced_insights(tables)
                print(adv["summary_text"])
                last_answer = adv["summary_text"]
            else:
                print("No table files found.")

            # LLM document summary
            if documents:
                combined_text = "\n\n".join(documents.values())
                q = "Provide a structured report, insights, trends, and conclusions from these documents."
                summary = ask_llm(q, context={"docs": combined_text}, model_name="gemma:2b")

                last_answer = summary
                print("\n--- DOCUMENT SUMMARY ---\n")
                print(summary)
            else:
                print("No documents to summarize.")

        # -------------------------------------------
        # OPTION 8 – PDF & Word File Question-Answering
        # -------------------------------------------
        elif choice == "8":
            folder = input("Enter folder path containing PDF/DOCX files: ").strip()

            print("\nExtracting text...\n")
            pdf_texts, docx_texts = extract_documents_from_folder(folder)

            if not pdf_texts and not docx_texts:
                print("No PDF or DOCX found.")
                continue

            combined_text = "\n\n".join(list(pdf_texts.values()) + list(docx_texts.values()))

            question = input("\nAsk a question based on the documents: ")
            answer = ask_llm(question, context={"documents": combined_text}, model_name="gemma:2b")

            last_answer = answer
            print("\n--- ANSWER ---\n")
            print(answer)

        # -------------------------------------------
        # OPTION 9 – Export Last AI Response
        # -------------------------------------------
        elif choice == "9":
            if not last_answer.strip():
                print("No AI response available to export.")
                continue

            print("\nChoose export format:")
            print("1. Excel")
            print("2. Word Document")
            print("3. Clean Tabulated Word Report")

            fmt = input("Enter option: ")

            os.makedirs(OUTPUT_FOLDER, exist_ok=True)

            if fmt == "1":
                path = os.path.join(OUTPUT_FOLDER, "ai_response.xlsx")
                export_to_excel(last_answer, path)
                print(f"Exported to {path}")

            elif fmt == "2":
                path = os.path.join(OUTPUT_FOLDER, "ai_response.docx")
                export_to_word(last_answer, path)
                print(f"Exported to {path}")

            elif fmt == "3":
                path = os.path.join(OUTPUT_FOLDER, "ai_clean_report.docx")
                export_tabulated_report(last_answer, path)
                print(f"Exported clean report to {path}")

            else:
                print("Invalid option.")

        # -------------------------------------------
        # INVALID OPTION
        # -------------------------------------------
        else:
            print("Invalid choice. Try again.")


if __name__ == "__main__":
    main()

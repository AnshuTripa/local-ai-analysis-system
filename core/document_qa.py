# core/document_qa.py
import os
import docx
from PyPDF2 import PdfReader

def extract_text_from_pdf(file_path):
    try:
        reader = PdfReader(file_path)
        pages = [page.extract_text() for page in reader.pages]
        return "\n".join([p for p in pages if p])
    except:
        return ""


def extract_text_from_docx(file_path):
    try:
        doc = docx.Document(file_path)
        return "\n".join([p.text for p in doc.paragraphs])
    except:
        return ""


def extract_documents_from_folder(folder_path):
    pdf_texts = {}
    docx_texts = {}

    for fname in os.listdir(folder_path):
        fpath = os.path.join(folder_path, fname)
        lname = fname.lower()

        if lname.endswith(".pdf"):
            pdf_texts[fname] = extract_text_from_pdf(fpath)

        elif lname.endswith(".docx"):
            docx_texts[fname] = extract_text_from_docx(fpath)

    return pdf_texts, docx_texts

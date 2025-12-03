# core/document_qa.py
import io
import re
from typing import Dict, List, Tuple, Any
import pdfplumber
from docx import Document
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel
import numpy as np
import math

# --------------------
# Extraction utilities
# --------------------
def extract_text_from_pdf_bytes(file_bytes: bytes) -> Dict[int, str]:
    """Return dict page_no -> text"""
    pages = {}
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                txt = page.extract_text() or ""
                pages[i] = txt
    except Exception:
        # fallback: try naive decode (rare)
        text = file_bytes.decode(errors="ignore")
        pages[1] = text
    return pages

def extract_text_from_docx_bytes(file_bytes: bytes) -> Dict[int, str]:
    """Return dict paragraph_index -> paragraph_text (we approximate pages with paragraphs)"""
    # python-docx requires a file-like object
    docs = {}
    try:
        f = io.BytesIO(file_bytes)
        doc = Document(f)
        # group paragraphs into pseudo-pages by chunking every ~40 paragraphs (approx)
        paras = [p.text for p in doc.paragraphs if p.text and p.text.strip()]
        # create pseudo-pages of ~40 paras to keep position info
        block_size = 40
        for i in range(0, len(paras), block_size):
            page_no = (i // block_size) + 1
            docs[page_no] = "\n".join(paras[i:i+block_size])
    except Exception:
        docs[1] = file_bytes.decode(errors="ignore")
    return docs

def extract_text_from_documents(raw_docs: Dict[str, bytes or str]) -> Dict[str, str]:
    """
    Accepts raw_docs: filename -> bytes (preferred) or str.
    Returns filename -> single string with page markers like [PAGE 3]...
    Also returns smaller pages/pseudo-pages so chunking later knows page numbers.
    """
    results = {}
    for fname, data in (raw_docs or {}).items():
        pages_map = {}
        # if already string, treat it as single page
        if isinstance(data, str):
            pages_map = {1: data}
        else:
            # try to guess by extension
            name_low = fname.lower()
            try:
                if name_low.endswith(".pdf"):
                    pages_map = extract_text_from_pdf_bytes(data)
                elif name_low.endswith(".docx"):
                    pages_map = extract_text_from_docx_bytes(data)
                else:
                    # fallback decode
                    pages_map = {1: data.decode(errors="ignore")}
            except Exception:
                pages_map = {1: (data.decode(errors="ignore") if isinstance(data, (bytes, bytearray)) else str(data))}

        # stitch pages into a single string with markers
        stitched = []
        for pno in sorted(pages_map.keys()):
            stitched.append(f"[PAGE {pno}]\n{pages_map[pno]}\n")
        results[fname] = "\n".join(stitched)
    return results

# --------------------
# Chunking + indexing
# --------------------
def chunk_text_with_refs(full_text: str, fname: str, chunk_size: int = 1000, overlap: int = 200) -> List[Dict[str, Any]]:
    """
    full_text contains markers like [PAGE X]. We chunk across the stitched text but retain
    metadata about which page marker appears in each chunk by scanning the substring.
    Returns list of chunks: {id, file, page_refs, start, end, text}
    """
    # Normalize whitespace
    txt = re.sub(r"\r\n", "\n", full_text)
    txt = re.sub(r"\n{2,}", "\n\n", txt)
    length = len(txt)
    chunks = []
    start = 0
    cid = 0
    while start < length:
        end = min(length, start + chunk_size)
        snippet = txt[start:end]
        # expand end to nearest sentence end (optional)
        # capture page numbers referenced in snippet
        page_refs = re.findall(r"\[PAGE\s+(\d+)\]", snippet, flags=re.IGNORECASE)
        page_refs = list(map(int, page_refs)) if page_refs else []
        clean_snippet = re.sub(r"\[PAGE\s+\d+\]", "", snippet, flags=re.IGNORECASE).strip()
        if clean_snippet:
            cid += 1
            chunks.append({
                "id": f"{fname}::chunk_{cid}",
                "file": fname,
                "pages": page_refs,
                "start": start,
                "end": end,
                "text": clean_snippet
            })
        start = end - overlap
        if start < 0:
            start = 0
    return chunks

def chunk_and_index_documents(docs_text: Dict[str, str], chunk_size: int = 1200, overlap: int = 250):
    """
    Given docs_text filename->stitched text, produce:
      - chunks (list of metadata dicts)
      - tfidf vectorizer and matrix for retrieval
    """
    all_chunks = []
    for fname, txt in docs_text.items():
        chunks = chunk_text_with_refs(txt, fname, chunk_size=chunk_size, overlap=overlap)
        all_chunks.extend(chunks)
    # Build TF-IDF over all chunk texts
    corpus = [c["text"] for c in all_chunks]
    if not corpus:
        return {"chunks": [], "vectorizer": None, "matrix": None}
    vectorizer = TfidfVectorizer(stop_words="english", max_features=20000)
    mat = vectorizer.fit_transform(corpus)  # shape (n_chunks, n_features)
    return {"chunks": all_chunks, "vectorizer": vectorizer, "matrix": mat}

# --------------------
# Retrieval + answer
# --------------------
def retrieve_top_chunks(question: str, index_struct: dict, top_k: int = 5):
    """
    Return top_k chunks (with score) given the question.
    """
    if not index_struct or not index_struct.get("matrix") or index_struct.get("matrix").shape[0] == 0:
        return []
    vec = index_struct["vectorizer"].transform([question])
    cosine_similarities = linear_kernel(vec, index_struct["matrix"]).flatten()
    top_indices = np.argsort(-cosine_similarities)[:top_k]
    results = []
    for idx in top_indices:
        score = float(cosine_similarities[idx])
        chunk = index_struct["chunks"][idx]
        results.append({
            "id": chunk["id"],
            "file": chunk["file"],
            "pages": chunk["pages"],
            "text": chunk["text"][:2000],
            "score": score
        })
    return results

def answer_from_doc_index(question: str, index_struct: dict, top_k: int = 6, concat_limit: int = 3000) -> dict:
    """
    Returns a grounded answer dict:
      { answer: str (concatenated snippet or ''), references: [ {file, pages, snippet, score} ] }
    This function does not call any LLM. It returns the retrieved snippets and references.
    """
    top = retrieve_top_chunks(question, index_struct, top_k=top_k)
    if not top:
        return {"answer": "No matching content found in documents.", "references": []}

    # Build grounded 'answer' by concatenating best snippets (limited length)
    parts = []
    refs = []
    total = 0
    for t in top:
        snippet = t["text"].strip()
        add = snippet if total + len(snippet) <= concat_limit else snippet[: max(0, concat_limit - total)]
        if add:
            parts.append(add)
            total += len(add)
        refs.append({"file": t["file"], "pages": t.get("pages", []), "snippet": snippet[:500], "score": t["score"]})
        if total >= concat_limit:
            break

    return {"answer": "\n\n".join(parts), "references": refs}

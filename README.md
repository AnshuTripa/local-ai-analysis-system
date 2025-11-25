🚀 Local AI Analysis System

Offline • Secure • Multi-File Analytics • Advanced Insights • LLM-Powered Reasoning

A fully offline, privacy-focused AI tool that analyzes Excel, CSV, PDF, Word, and Text files using powerful local LLMs such as Gemma, Mistral, and Llama 3 (via Ollama).
Designed for shipping, marine operations, maintenance teams, and data analysts who need fast, secure, and smart insights — without sending data online.

⭐ Key Features
🔥 1. Powerful Offline LLM Integration

Runs completely offline using Ollama and supports models like:

Gemma 2B

Mistral

Llama 3 / Llama 3.2

Other high-reasoning models

Enables:

Deep analysis

Smart summaries

Context-aware recommendations

PDF/Word Q&A

📊 2. Advanced Data Insights & Reasoning

The system automatically generates:

Smart summaries

Trends and pattern detection

Exceptions and anomaly identification

Equipment risk scoring

Maintenance recommendations

KPI dashboards

📁 3. Folder-Based Analysis

Choose any folder on your computer — the system automatically reads:

Excel (.xlsx, .xls)

CSV

PDF

Word (.docx)

Text (.txt)

No manual selection needed.

📄 4. PDF & Word File Question-Answering

Ask questions like:

“Summarize this document”

“What are the key issues?”

“Extract important deadlines”

“What corrective actions are recommended?”

The system extracts text and generates accurate answers.

📤 5. Export Answers

All AI-generated results can be exported to:

Excel Reports

Word Reports

Structured Tabulated Reports

Perfect for sending to clients, ship managers, or audit teams.

⚡ 6. One-Time Cleaning Logic

If a file is already cleaned, the system:

Skips reprocessing

Saves time

Improves performance

Ideal for recurring folder scans.

🚀 7. Performance Optimizations

Faster file loading

Reduced memory usage

Improved merging pipeline

Efficient LLM calls

📘 8. Shipping Terminology Learning Table

A file named learning_table.csv allows you to teach the AI:

Marine terminology

Shipping abbreviations

Vessel maintenance codes

Example:

HFO, Heavy Fuel Oil  
ETA, Estimated Time of Arrival  
RPM, Revolutions Per Minute  


The AI automatically references this table when generating insights.

🧠 Menu Options
1 → Practical Insights (Maintenance + Replacement)
2 → Ask a Question (LLM)
3 → Exit
4 → Preview Cleaned Data
5 → Export Cleaned Files
6 → Advanced Insights & Reasoning
7 → Folder-Based Analysis
8 → PDF & Word Q&A
9 → Export AI Responses

🛠️ Installation & Setup
1️⃣ Clone the Repository
git clone https://github.com/AnshuTripa/local-ai-analysis-system.git
cd local-ai-analysis-system

2️⃣ Create Virtual Environment
python -m venv venv
venv\Scripts\activate    # For Windows

3️⃣ Install Requirements
pip install -r requirements.txt

4️⃣ Install Ollama (Required)

Download: https://ollama.com/download

Then install models like:

ollama pull gemma:2b
ollama pull mistral
ollama pull llama3.2

5️⃣ Run the System
python main.py

📦 Project Structure
/core
    analyzer.py
    cleaner.py
    file_loader.py
    llm_engine.py
    exporter.py
data/
output/
learning_table.csv
main.py
README.md
requirements.txt

👨‍💻 Author

Anshu Tripathi
AI Developer | MCA | Data Science & Python Specialist
🌐 GitHub: AnshuTripa

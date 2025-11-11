📄 Invoice Data Extractor (Gemini + Streamlit)

An AI-powered Invoice Data Extraction Tool built with Streamlit and Google Gemini 2.5 Flash.
This app automatically extracts structured invoice data from uploaded PDFs and maps it to a provided Excel template.

It supports automatic field detection, template alignment, JSON data extraction, and direct Excel/ZIP downloads — all through a clean web interface.

🚀 Features

✅ Upload invoice PDFs and Excel templates
✅ Preview PDF pages directly in the browser
✅ Generate AI-based JSON extraction structure (sub-prompt)
✅ Extract structured data using Gemini 2.5 Flash
✅ Automatically format output as per the Excel template
✅ Adds serial numbers dynamically (S.No: 1, 2, 3, …)
✅ Download extracted data as Excel or a ZIP bundle (PDF + Excel)
✅ Auto-refreshes when a new PDF is uploaded

🧩 Tech Stack
Component	Technology
Frontend	Streamlit

AI Model	Google Gemini 2.5 Flash

PDF Processing	PyMuPDF (fitz)

Image Handling	Pillow (PIL)

Data Manipulation	Pandas

Excel Handling	openpyxl

Environment Management	python-dotenv
🧰 Installation
1️⃣ Clone the Repository
git clone https://github.com/yourusername/invoice-data-extractor.git
cd invoice-data-extractor

2️⃣ Create & Activate Virtual Environment
python -m venv venv
venv\Scripts\activate  # On Windows
# OR
source venv/bin/activate  # On macOS/Linux

3️⃣ Install Dependencies
pip install -r requirements.txt


Example requirements.txt:

streamlit
pandas
fitz
PyMuPDF
Pillow
python-dotenv
openpyxl
google-generativeai

4️⃣ Configure Gemini API Key

Create a .env file in the project root:

GEMINI_API_KEY=your_google_gemini_api_key_here


Get your API key from Google AI Studio
.

🖥️ Usage
Run the Streamlit App
streamlit run app.py


Then open the displayed URL (usually http://localhost:8501
).

📚 How It Works

Upload Files

Upload a PDF invoice and a sample Excel template (with headers).

Generate Sub Prompt

Click “🔍 Generate Sub Prompt from Template” to see or edit the extraction structure.

Extract Data

Click “⚙️ Extract Template Mapping” to run Gemini and map extracted values.

Review Output

Review results in a dataframe table.

Download Files

Download results as an Excel file or combined ZIP (PDF + Excel).

📄 Example Extraction Schema
{
  "S.No": 1,
  "Memo #": "",
  "Vendor Name": "<payable_to>",
  "Service Address": "<sites: [{address}]>",
  "Inv #": "<invoice_number>",
  "Inv Date": "<invoice_date>",
  "Due Date": "<due_date>",
  "Amt": "<invoice_total_amount>"
}


✅ The AI ensures:

Sequential serial numbers (1, 2, 3, …)

Matching fields to your Excel template

Only valid JSON responses

⚙️ Auto-Refresh Logic

Whenever a new PDF is uploaded:

Previous extraction results are cleared

The interface resets for a new run

Prevents mismatched data between invoices

🧠 Notes

Works best with readable PDFs (text-based, not handwritten).

Gemini handles OCR internally — no need for Tesseract or external OCR tools.

If your Excel template has specific headers, they’ll be dynamically aligned to extracted fields.

📦 Output Files
File	Description
*_template_mapping.xlsx	Extracted and structured invoice data
*_template_bundle.zip	Bundle with both original PDF and Excel result
🧑‍💻 Developer Info

Author: Mohammed Ajmal

Python Version: 3.10+

Framework: Streamlit

AI Model: Gemini 2.5 Flash

🧾 License

This project is licensed under the MIT License — feel free to use and modify it for your own projects.

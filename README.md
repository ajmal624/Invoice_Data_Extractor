# 📄 Invoice Data Extractor (Streamlit + OpenAI)

A powerful **Streamlit-based invoice data extraction tool** that reads PDF invoices, extracts fields using the OpenAI Vision API, and exports both **summary data** and a **custom Excel template** — all in one clean interface.

---

## 🚀 Features

- 📤 Upload invoice PDFs
- 🔍 Extract invoice details (vendor, invoice number, amount, site info, due dates)
- 🧩 Smart due date computation logic
- 🪄 Auto-generates both:
  - **Summary & Items Sheet**
  - **Custom Template**
- 📊 Dual-pane Streamlit layout with side-by-side dataframes
- ⬇️ Download Excel & ZIP bundles for both outputs

---

## 🧱 Tech Stack

- **Python 3.10+**
- **Streamlit** — Web interface
- **OpenAI API** — Vision + JSON extraction
- **PyMuPDF** — PDF → image conversion
- **Pandas / OpenPyXL** — Excel export

---

## ⚙️ Setup Instructions

### 1️⃣ Clone this Repository
```bash
git clone https://github.com/<your-username>/invoice-data-extractor.git
cd invoice-data-extractor
# 4️⃣ Add your OpenAI API key securely
Go to Streamlit Cloud > App Settings > Secrets > Add:

OPENAI_API_KEY = "your_openai_api_key_here"

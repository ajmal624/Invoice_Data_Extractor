import os
import re
import json
import base64
import fitz  # PyMuPDF
import streamlit as st
import pandas as pd
import zipfile
from dotenv import load_dotenv
import OpenAI
from io import BytesIO
from PIL import Image
from datetime import datetime, timedelta

# ========= CONFIG =========
load_dotenv()

# ✅ Load OpenAI API key from Streamlit Secrets
OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
openai.api_key = OPENAI_API_KEY

# Optional: validate key
if not OPENAI_API_KEY or not OPENAI_API_KEY.startswith("sk-"):
    st.error("❌ Missing or invalid OpenAI API key in Streamlit secrets.")
    st.stop()
client = OpenAI(api_key=OPENAI_API_KEY)

# ========= STREAMLIT UI =========
st.set_page_config(page_title="📄 Invoice Data Extractor", layout="wide")
st.title("📄 Invoice Data Extractor")

uploaded_file = st.file_uploader("📤 Upload your PDF file", type=["pdf"])

# ========= SESSION STATE =========
for key in ["parsed_data", "df_summary", "items_df", "df_custom"]:
    if key not in st.session_state:
        st.session_state[key] = None

# ========= HELPERS =========
def pdf_to_images(pdf_bytes, dpi=300):
    pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")
    images = []
    for i in range(len(pdf_document)):
        pix = pdf_document.load_page(i).get_pixmap(dpi=dpi)
        img = Image.open(BytesIO(pix.tobytes("png"))).convert("RGB")
        images.append(img)
    pdf_document.close()
    return images

def encode_image_b64(pil_img):
    buf = BytesIO()
    pil_img.save(buf, format="PNG", optimize=True)
    return f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}"

def clean_json_output(raw_text):
    if not raw_text:
        return {"error": "no output"}
    text = re.sub(r"^```(?:json)?", "", raw_text.strip(), flags=re.MULTILINE)
    text = re.sub(r"```$", "", text.strip())
    text = text.replace("\n", " ").strip()
    try:
        return json.loads(text)
    except Exception:
        try:
            text_fixed = re.sub(r"([{,])\s*([A-Za-z0-9_]+):", r'\1 "\2":', text)
            return json.loads(text_fixed)
        except Exception as e2:
            return {"error": f"JSON parse failed: {e2}", "raw": text}

def flatten_dict(d, parent_key="", sep="_"):
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)

def separate_summary_and_items(parsed_data):
    flat_data = {}
    items_df = pd.DataFrame()
    for key, val in parsed_data.items():
        if isinstance(val, list) and all(isinstance(i, dict) for i in val):
            items_df = pd.concat([items_df, pd.DataFrame(val)], ignore_index=True)
        elif isinstance(val, dict):
            flat_data.update(flatten_dict(val, key))
        else:
            flat_data[key] = val
    df_summary = pd.DataFrame(list(flat_data.items()), columns=["Field Name", "Value"])
    return df_summary, items_df

def create_excel_workbook(df_summary, items_df, pdf_name):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df_summary.to_excel(writer, index=False, sheet_name="Summary")
        if not items_df.empty:
            items_df.to_excel(writer, index=False, sheet_name="Items")
    output.seek(0)
    return output

def create_zip_with_files(pdf_bytes, excel_bytes, pdf_name, excel_name):
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(pdf_name, pdf_bytes)
        z.writestr(excel_name, excel_bytes.getvalue())
    zip_buffer.seek(0)
    return zip_buffer

def deep_get(data, path, default="Not Found"):
    keys = path.split(".")
    for k in keys:
        if isinstance(data, dict) and k in data:
            data = data[k]
        else:
            return default
    return data

# ========= PROMPT =========
default_prompt = """
SYSTEM:
You are a professional invoice data extractor. Always return valid JSON only — no markdown, no explanations, and no extra keys.
If a field is missing, set its value to "Not Found".
Dates must always be in ISO `YYYY-MM-DD` format when possible.

USER:
Extract all invoice-level and site-level fields from the provided document (image or text) and return JSON exactly in this format:

{
  "billing_details": {"payable_to": "<vendor name or 'Not Found'>"},
  "invoice": {
      "invoice_number": "<string or 'Not Found'>",
      "invoice_date": "<YYYY-MM-DD or 'Not Found'>",
      "amount": "<string or 'Not Found'>"
  },
  "payment_due_by": "<YYYY-MM-DD or 'Not Found'>",
  "sites": [
    {"address": "<address string or 'Not Found'>", "date": "<YYYY-MM-DD or 'Not Found'>", "alternative_date": "<YYYY-MM-DD or 'Not Found'>" }
  ],
  "computed_due_date": "<YYYY-MM-DD or 'Not Found'>"
}

MANDATORY DUE DATE LOGIC:
1️⃣ If `payment_due_by` exists and is not "Not Found":
    → computed_due_date = payment_due_by
2️⃣ Else if `payment_due_by` is "Not Found" but `invoice.invoice_date` (or `invoice_invoice_date`) exists:
    → computed_due_date = invoice_date + 30 calendar days
3️⃣ Else:
    → computed_due_date = "Not Found"

ADDITIONAL RULES:
- Always prefer `invoice.invoice_date` over `invoice_invoice_date` if both exist.
- Convert all date strings to `YYYY-MM-DD` format where possible.
- If any date cannot be parsed, return "Not Found".

- If the invoice or site section contains a date range in this format:
     "Sep 01/25 - Sep 30/25" or "09/01/25 - 09/30/25",
     extract and show this full range value (as-is) as the "invoice_date" or "date" — this is mandatory.
- Otherwise, if the site date appears as a single date (e.g., "05/01/25", "08/31/2025", "09/18/2025"), use that single date.

- Ignore ambiguous or partial values such as "11 - Sep" (treat them as "Not Found").

- The field "Amt" in the final output must always display the **Invoice Total** (not "Amount Due").

- In Discover Fields, also create a new field called `"alternative_date"` under each site entry with the following rules:
    • If the site `date` starts with `01`, ignore it (do not create an alternative date).
    • If the site `date` starts from `02` to `31`, change it to the **first day (01)** of the **next month**.
      (For example, if `invoice_invoice_date` = "2025-09-18", then `"alternative_date"` = "2025-10-01".)
    • If `"alternative_date"` appears in the site details, then the `computed_due_date` must be set as
      **30 calendar days from the actual `invoice_invoice_date`**.

- If in Discover Fields the value of `payment_due_by` is a valid date and it occurs **before** (earlier than) any site's `date`, then override the due date logic and set `computed_due_date` to exactly **31 calendar days after** the actual `payment_due_by` date.  
  Always perform real calendar date addition (not month replacement).  
  Example: if `site.date` = "2025-09-01" and `payment_due_by` = "2025-08-16", then `computed_due_date` = "2025-09-16".

- Do NOT include extra keys like “due_date_source”.
- Do NOT add markdown, commentary, or text outside the JSON.

FEW-SHOT EXAMPLES (follow pattern exactly):

Example A:
{
  "billing_details": {"payable_to": "Acme Corp"},
  "invoice": {"invoice_number": "INV-123", "invoice_date": "2025-09-01", "amount": "$1,200.00"},
  "payment_due_by": "2025-09-30",
  "sites": [{"address": "Houston TX", "date": "2025-09-01", "alternative_date": "Not Found"}],
  "computed_due_date": "2025-09-30"
}

Example B:
{
  "billing_details": {"payable_to": "Beta LLC"},
  "invoice": {"invoice_number": "INV-456", "invoice_date": "2025-09-10", "amount": "$900.00"},
  "payment_due_by": "Not Found",
  "sites": [{"address": "Dallas TX", "date": "2025-09-10", "alternative_date": "Not Found"}],
  "computed_due_date": "2025-10-10"
}

Example C:
{
  "billing_details": {"payable_to": "Frontier Waste"},
  "invoice": {"invoice_number": "INV-789", "invoice_date": "Not Found", "amount": "$2,500.00"},
  "payment_due_by": "Not Found",
  "sites": [],
  "computed_due_date": "Not Found"
}

Return **only** valid JSON.
"""

# ========= MAIN =========
if uploaded_file:
    pdf_bytes = uploaded_file.read()
    pdf_filename = uploaded_file.name
    images = pdf_to_images(pdf_bytes)

    st.markdown(
        f'<iframe src="data:application/pdf;base64,{base64.b64encode(pdf_bytes).decode()}" width="100%" height="600"></iframe>',
        unsafe_allow_html=True,
    )

    st.subheader("⚙️ Output")
    output_btn = st.button("🚀 Generate Output")

    if output_btn:
        try:
            image_entries = [{"type": "image_url", "image_url": {"url": encode_image_b64(img)}} for img in images]
            with st.spinner("🧠 Extracting data..."):
                response = openai.ChatCompletion.create(
                    model="gpt-4.1-mini",
                    temperature=0,
                    messages=[
                        {"role": "system", "content": "Return valid JSON only."},
                        {"role": "user", "content": [{"type": "text", "text": default_prompt}, *image_entries]},
                    ],
                )

            raw_output = response["choices"][0]["message"]["content"]
            parsed = clean_json_output(raw_output)
            st.session_state["parsed_data"] = parsed
            df_summary, items_df = separate_summary_and_items(parsed)
            st.session_state["df_summary"], st.session_state["items_df"] = df_summary, items_df

            # === Generate Custom Template ===
            vendor = deep_get(parsed, "billing_details.payable_to")
            inv_no = deep_get(parsed, "invoice.invoice_number")
            amount = deep_get(parsed, "invoice.amount")
            due = deep_get(parsed, "computed_due_date")
            sites = parsed.get("sites", [])
            records = []
            for i, s in enumerate(sites, 1):
                inv_date = s.get("alternative_date") if s.get("alternative_date") not in ["Not Found", None] else s.get("date", "Not Found")
                records.append({
                    "S. No": i,
                    "Vendor Name": vendor,
                    "Address": s.get("address", "Not Found"),
                    "Inv #": inv_no,
                    "Memo #": "Not Found",
                    "Inv Date": inv_date,
                    "Due Date": due,
                    "Invoice Total": amount
                })
            df_custom = pd.DataFrame(records)
            st.session_state["df_custom"] = df_custom

            # === Dual Column Display ===
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("📋 Summary & Items")
                st.dataframe(df_summary, height=250)
                if not items_df.empty:
                    st.dataframe(items_df, height=250)
                excel_bytes = create_excel_workbook(df_summary, items_df, pdf_filename)
                zip_buffer = create_zip_with_files(pdf_bytes, excel_bytes, pdf_filename, f"{pdf_filename.split('.')[0]}_alldata.xlsx")
                st.download_button("⬇️ Download Excel (All Data)", excel_bytes, f"{pdf_filename.split('.')[0]}_alldata.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                st.download_button("🗜️ Download ZIP (PDF + All Data)", zip_buffer, f"{pdf_filename.split('.')[0]}_alldata_bundle.zip", mime="application/zip")

            with col2:
                st.subheader("🧩 Custom Template")
                st.dataframe(df_custom, height=500)
                output = BytesIO()
                with pd.ExcelWriter(output, engine="openpyxl") as writer:
                    df_custom.to_excel(writer, index=False, sheet_name="Custom_Template")
                output.seek(0)
                zip_buffer2 = create_zip_with_files(pdf_bytes, output, pdf_filename, "custom_template.xlsx")
                st.download_button("📕 Download Custom Excel", output, f"{pdf_filename.split('.')[0]}_custom_template.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                st.download_button("🗜️ Download ZIP (PDF + Custom Excel)", zip_buffer2, f"{pdf_filename.split('.')[0]}_custom_bundle.zip", mime="application/zip")

        except Exception as e:

            st.error(f"❌ Error: {e}")






import os
import re
import io
import json
import base64
import zipfile
import fitz  # PyMuPDF
import pandas as pd
import streamlit as st
from io import BytesIO
from PIL import Image
from dotenv import load_dotenv
import google.generativeai as genai  # pyright: ignore[reportMissingImports]

# ================= GEMINI CONFIG =================
try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
except KeyError:
    st.error("❌ Missing Gemini API Key in Streamlit secrets. Please set it under `[secrets] GEMINI_API_KEY='your_key_here'`.")
    st.stop()

genai.configure(api_key=GEMINI_API_KEY)
MODEL_NAME = "gemini-2.5-flash"

# ================= STREAMLIT CONFIG =================
st.set_page_config(page_title="📄 Invoice Data Extractor", layout="wide")
st.title("📄 Invoice Data Extractor")

# ================= SESSION STATE =================
for key in ["sub_prompt", "parsed_data", "df_summary", "show_sub_prompt", "last_pdf_name"]:
    if key not in st.session_state:
        st.session_state[key] = None if key not in ["show_sub_prompt"] else False

# ================= FILE UPLOAD =================
col1, col2 = st.columns(2)
with col1:
    uploaded_pdf = st.file_uploader("📤 Upload Invoice PDF", type=["pdf"], key="pdf_upload")
with col2:
    uploaded_template = st.file_uploader("📋 Upload Excel Template", type=["xlsx"], key="excel_upload")

# ================= FILE CHANGE DETECTION =================
if uploaded_pdf:
    current_pdf_name = uploaded_pdf.name
    if st.session_state.last_pdf_name != current_pdf_name:
        st.session_state.parsed_data = None
        st.session_state.df_summary = None
        st.session_state.show_sub_prompt = False
        st.session_state.last_pdf_name = current_pdf_name

# ================= HELPERS =================
def pdf_to_images(pdf_bytes, dpi=250):
    pdf_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    imgs = []
    for i in range(len(pdf_doc)):
        pix = pdf_doc.load_page(i).get_pixmap(dpi=dpi)
        img = Image.open(BytesIO(pix.tobytes("png"))).convert("RGB")
        imgs.append(img)
    pdf_doc.close()
    return imgs

def clean_json_output(raw_text):
    if not raw_text:
        return {"error": "Empty response"}
    text = re.sub(r"^```(?:json)?|```$", "", raw_text.strip(), flags=re.MULTILINE)
    text = text.replace("\n", " ").strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return {"data": parsed}
        return parsed
    except Exception:
        try:
            fixed = re.sub(r"([{,])\s*([A-Za-z0-9_]+):", r'\1 "\2":', text)
            parsed = json.loads(fixed)
            if isinstance(parsed, list):
                return {"data": parsed}
            return parsed
        except Exception as e2:
            return {"error": f"JSON parse failed: {e2}", "raw": text}

def expand_addresses(df):
    if "Service Address" in df.columns:
        df = df.explode("Service Address")
    return df

def normalize_none_values(df):
    return df.fillna("Not Found").replace("", "Not Found")

def remove_duplicate_columns(df):
    seen = {}
    cols_to_keep = []
    for col in df.columns:
        if col not in seen:
            seen[col] = df[col]
            cols_to_keep.append(col)
        else:
            existing_valid = seen[col].replace("Not Found", pd.NA).dropna().shape[0]
            new_valid = df[col].replace("Not Found", pd.NA).dropna().shape[0]
            if new_valid > existing_valid:
                seen[col] = df[col]
                cols_to_keep[-1] = col
    clean_df = pd.DataFrame({c: seen[c] for c in cols_to_keep})
    return clean_df

def add_serial_numbers(df, template_cols):
    serial_values = list(range(1, len(df) + 1))
    if "S.No" in df.columns:
        df["S.No"] = serial_values
    else:
        df.insert(0, "S.No", serial_values)

    if "S.No" in template_cols:
        ordered_cols = [c for c in template_cols if c in df.columns]
        missing_cols = [c for c in df.columns if c not in ordered_cols]
        df = df[ordered_cols + missing_cols]
    else:
        df = df[["S.No"] + [c for c in df.columns if c != "S.No"]]
    return df

def make_excel(df):
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Extracted_Data")
    buf.seek(0)
    return buf

def make_zip(pdf_bytes, excel_bytes, pdf_name, excel_name):
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(pdf_name, pdf_bytes)
        z.writestr(excel_name, excel_bytes.getvalue())
    buf.seek(0)
    return buf

# ================= MAIN PROCESS =================
if uploaded_pdf and uploaded_template:
    st.success("✅ Files uploaded successfully.")
    pdf_name = uploaded_pdf.name
    pdf_bytes = uploaded_pdf.read()

    st.subheader("📘 Uploaded Files Preview")
    colA, colB = st.columns(2)

    with colA:
        st.write(f"**Invoice PDF:** {pdf_name}")
        pdf_doc = fitz.open(stream=pdf_bytes, filetype="pdf")

        pdf_images_preview = []
        pdf_images = []
        for i in range(len(pdf_doc)):
            page = pdf_doc.load_page(i)
            pix = page.get_pixmap(dpi=150)
            img_bytes = pix.tobytes("png")
            pdf_images_preview.append(img_bytes)
            pdf_images.append(Image.open(BytesIO(img_bytes)).convert("RGB"))

        scroll_height = 600
        pdf_html = f"<div style='height:{scroll_height}px; overflow-y:scroll; border:1px solid #444; padding:10px;'>"
        for idx, img_data in enumerate(pdf_images_preview, start=1):
            b64_img = base64.b64encode(img_data).decode()
            pdf_html += f"<img src='data:image/png;base64,{b64_img}' style='width:100%; margin-bottom:10px; border-radius:8px; box-shadow:0 0 4px rgba(0,0,0,0.2);' alt='Page {idx}'/>"
        pdf_html += "</div>"
        st.markdown(pdf_html, unsafe_allow_html=True)

    with colB:
        st.write(f"**Excel Template:** {uploaded_template.name}")
        df_template = pd.read_excel(uploaded_template)
        st.dataframe(df_template.head())

    # ================= SUB PROMPT SECTION =================
    if not st.session_state.show_sub_prompt:
        if st.button("🔍 Generate Sub Prompt from Template", key="generate_subprompt"):
            st.session_state.show_sub_prompt = True

    if st.session_state.show_sub_prompt:
        st.subheader("🧩 Sub Prompt (JSON Extraction Structure)")

        if st.session_state.sub_prompt is None:
            st.session_state.sub_prompt = """
{
  "S.No": i,
  "Memo #": "",
  "Vendor Name": "<payable_to>",
  "Service Address": "<sites: [{address}]>",
  "Inv #": "<invoice_number>",
  "Inv Date": "<invoice_date>",
  "Due Date": "<due_date>",
  "Amt": "<invoice_total_amount>"
}
Return only valid JSON.
Ensure "S.No" starts at 1 and increments sequentially.
"""

        # Sub Prompt Text Box
        st.session_state.sub_prompt = st.text_area(
            "Edit or regenerate this JSON structure:",
            st.session_state.sub_prompt,
            height=260,
            key="sub_prompt_area"
        )

        # Lower-right aligned "Regenerate" button using CSS
        st.markdown(
            """
            <style>
            div[data-testid="stHorizontalBlock"] > div:nth-child(2) button {
                float: right !important;
                margin-top: -45px;
                background-color: #4CAF50 !important;
                color: white !important;
                border-radius: 8px;
                border: none;
            }
            </style>
            """,
            unsafe_allow_html=True
        )

        regen_col1, regen_col2 = st.columns([0.7, 0.3])
        with regen_col2:
            if st.button("🔄 Regenerate Sub Prompt using Gemini", key="regen_prompt"):
                with st.spinner("Generating sub prompt dynamically using Gemini..."):
                    main_prompt = f"""
You are a professional invoice data extraction assistant.
Analyze the invoice and the following Excel template columns:
{list(df_template.columns)}

Generate a JSON extraction structure suitable for this template.
Ensure "S.No" starts at 1 and increments sequentially.

Example:
{st.session_state.sub_prompt}

Return only valid JSON — no markdown or explanations.
"""
                    model = genai.GenerativeModel(MODEL_NAME)
                    response = model.generate_content(main_prompt)
                    st.session_state.sub_prompt = response.text.strip()
                    st.success("✅ Sub prompt updated dynamically based on Excel template!")

        if st.button("⚙️ Extract Template Mapping", key="extract_btn"):
            with st.spinner("Extracting structured data using Gemini..."):
                extraction_prompt = f"""
Use this JSON structure to extract all data from the invoice images and map it to the Excel template fields.

{st.session_state.sub_prompt}

Ensure:
- "S.No" starts from 1 and increments by 1.
- Return only valid JSON — no markdown or explanations.
"""
                model = genai.GenerativeModel(MODEL_NAME)
                response2 = model.generate_content([extraction_prompt] + [img for img in pdf_images])
                raw_out = response2.text
                parsed = clean_json_output(raw_out)
                st.session_state.parsed_data = parsed

            data = parsed.get("data") if isinstance(parsed, dict) and "data" in parsed else parsed
            if not data or isinstance(data, dict):
                df = pd.DataFrame([data])
            else:
                df = pd.DataFrame(data)

            all_template_cols = list(df_template.columns)
            for col in all_template_cols:
                if col not in df.columns:
                    df[col] = "Not Found"

            df = remove_duplicate_columns(df)
            df = add_serial_numbers(df, all_template_cols)
            df = normalize_none_values(df)
            df = expand_addresses(df)

            st.session_state.df_summary = df

        # ================= SHOW OUTPUT WITHOUT REFRESH =================
        if st.session_state.df_summary is not None:
            st.subheader("📋 Extracted Data (Template Mapping)")
            st.dataframe(st.session_state.df_summary, use_container_width=True)

            excel_bytes = make_excel(st.session_state.df_summary)
            zip_buf = make_zip(pdf_bytes, excel_bytes, pdf_name, f"{pdf_name.split('.')[0]}_mapped.xlsx")

            st.download_button(
                "⬇️ Download Excel (Template Mapping)",
                data=excel_bytes,
                file_name=f"{pdf_name.split('.')[0]}_template_mapping.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="download_excel",
                use_container_width=True
            )

            st.download_button(
                "📦 Download ZIP (PDF + Excel)",
                data=zip_buf,
                file_name=f"{pdf_name.split('.')[0]}_template_bundle.zip",
                mime="application/zip",
                key="download_zip",
                use_container_width=True
            )

else:
    st.info("⬆️ Please upload both the PDF and Excel template to begin.")

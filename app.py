import streamlit as st
import google.generativeai as genai
import pandas as pd
import docx
import fitz  # PyMuPDF
import io
import re

# --- Konfigurasi Awal ---
st.set_page_config(
    page_title="Proofreader Bahasa Indonesia",
    page_icon="",
    layout="wide"
)

st.title("Proofreader Bahasa Indonesia (KBBI & PUEBI)")
st.caption("Unggah dokumen (PDF/DOCX) untuk mendeteksi kesalahan ketik dan ejaan.")

try:
    api_key = st.secrets["AIzaSyDR2v7zE4r1dtSlNUGmDuHQSssMT9P4X2E"]
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-flash-latest')
except Exception:
    st.error("Google API Key belum diatur. Harap atur di st.secrets.", icon="")
    st.stop()


# --- FUNGSI-FUNGSI UTAMA ---

def extract_text_with_pages(uploaded_file):
    """Mengekstrak teks dari file PDF atau DOCX beserta nomor halamannya."""
    pages_content = []
    file_extension = uploaded_file.name.split('.')[-1].lower()
    
    # Baca file stream ke dalam bytes
    file_bytes = uploaded_file.getvalue()

    if file_extension == 'pdf':
        try:
            pdf_document = fitz.open(stream=file_bytes, filetype="pdf")
            for page_num, page in enumerate(pdf_document):
                pages_content.append({"halaman": page_num + 1, "teks": page.get_text()})
            pdf_document.close()
        except Exception as e:
            st.error(f"Gagal membaca file PDF: {e}")
            return None
            
    elif file_extension == 'docx':
        try:
            # DOCX tidak memiliki konsep 'halaman' yang eksplisit seperti PDF.
            # Kita akan anggap seluruh dokumen sebagai satu halaman besar untuk analisis.
            doc = docx.Document(io.BytesIO(file_bytes))
            full_text = "\n".join([para.text for para in doc.paragraphs])
            pages_content.append({"halaman": 1, "teks": full_text})
        except Exception as e:
            st.error(f"Gagal membaca file DOCX: {e}")
            return None
    else:
        st.error("Format file tidak didukung. Harap unggah .pdf atau .docx")
        return None
        
    return pages_content

def proofread_with_gemini(text_to_check):
    """Mengirim teks ke Gemini untuk proofreading dan mem-parsing hasilnya."""
    if not text_to_check or text_to_check.isspace():
        return []

    # Prompt yang dirancang untuk mendapatkan output terstruktur
    prompt = f"""
    Anda adalah seorang editor dan ahli bahasa Indonesia profesional yang sangat teliti.
    Tugas Anda adalah melakukan proofread pada teks berikut.
    Fokus utama Anda adalah:
    1. Memperbaiki kesalahan ketik (typo).
    2. Memastikan semua kata sesuai dengan Kamus Besar Bahasa Indonesia (KBBI).
    3. Memperbaiki kesalahan tata bahasa sederhana dan ejaan agar sesuai dengan Pedoman Umum Ejaan Bahasa Indonesia (PUEBI).

    PENTING: Berikan hasil dalam format yang ketat. Untuk setiap kesalahan, gunakan format:
    [SALAH] kata atau frasa yang salah -> [BENAR] kata atau frasa perbaikan

    Jika tidak ada kesalahan sama sekali, kembalikan teks: "TIDAK ADA KESALAHAN"

    Berikut adalah teks yang harus Anda periksa:
    ---
    {text_to_check}
    """
    
    try:
        response = model.generate_content(prompt)
        # Regex untuk mem-parsing output: [SALAH] ... -> [BENAR] ...
        pattern = re.compile(r"\[SALAH\]\s*(.*?)\s*->\s*\[BENAR\]\s*(.*?)\s*\n", re.IGNORECASE)
        found_errors = pattern.findall(response.text)
        
        # Mengembalikan daftar tuple (salah, benar)
        return [{"salah": salah.strip(), "benar": benar.strip()} for salah, benar in found_errors]
    except Exception as e:
        st.error(f"Terjadi kesalahan saat menghubungi AI: {e}")
        return []

def convert_df_to_excel(df):
    """Mengonversi DataFrame ke format Excel dalam memory."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Hasil Proofread')
    processed_data = output.getvalue()
    return processed_data


# --- ANTARMUKA STREAMLIT ---
uploaded_file = st.file_uploader(
    "Pilih file PDF atau DOCX",
    type=['pdf', 'docx'],
    help="File yang diunggah akan dianalisis untuk menemukan kesalahan ejaan dan ketik."
)

if uploaded_file is not None:
    st.info(f"File yang diunggah: **{uploaded_file.name}**")

    # Tombol untuk memulai proses analisis
    if st.button("🔍 Mulai Analisis", type="primary"):
        with st.spinner("Membaca dan mengekstrak teks dari dokumen..."):
            document_pages = extract_text_with_pages(uploaded_file)
        
        if document_pages:
            st.success("Ekstraksi teks berhasil. Dokumen memiliki {} halaman.".format(len(document_pages)))
            
            all_errors = []
            
            # Progress bar untuk memantau proses analisis per halaman
            progress_bar = st.progress(0, text="Menganalisis teks dengan AI...")
            
            for i, page in enumerate(document_pages):
                # Update progress bar
                progress_text = f"Menganalisis Halaman {page['halaman']}..."
                progress_bar.progress((i + 1) / len(document_pages), text=progress_text)
                
                # Kirim teks per halaman ke AI
                found_errors_on_page = proofread_with_gemini(page['teks'])
                
                # Jika ada kesalahan ditemukan, tambahkan nomor halaman dan simpan
                for error in found_errors_on_page:
                    all_errors.append({
                        "Kata/Frasa Salah": error['salah'],
                        "Perbaikan Sesuai KBBI": error['benar'],
                        "Ditemukan di Halaman": page['halaman']
                    })

            progress_bar.empty() # Hapus progress bar setelah selesai

            if not all_errors:
                st.success("Tidak ada kesalahan ejaan atau ketik yang ditemukan dalam dokumen.")
            else:
                st.warning(f"Ditemukan **{len(all_errors)}** potensi kesalahan dalam dokumen.")
                
                # Buat DataFrame dari hasil
                df = pd.DataFrame(all_errors)
                
                # Tampilkan tabel hasil di aplikasi
                st.dataframe(df, use_container_width=True)
                
                # Siapkan file Excel untuk diunduh
                excel_data = convert_df_to_excel(df)
                
                st.download_button(
                    label="Unduh Hasil sebagai Excel",
                    data=excel_data,
                    file_name=f"hasil_proofread_{uploaded_file.name.split('.')[0]}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
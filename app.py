from flask import Flask, render_template, request, send_file, jsonify
import fitz
from PIL import Image, ImageOps
import io
import zipfile
import uuid

app = Flask(__name__)

# Temporary in-memory storage for generated files
generated_files = {}

def invert_pdf_colors(input_pdf_bytes):
    doc = fitz.open(stream=input_pdf_bytes, filetype="pdf")
    new_doc = fitz.open()
    for page in doc:
        pix = page.get_pixmap(matrix=fitz.Matrix(1.0, 1.0))
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        inverted = ImageOps.invert(img)
        img_byte = io.BytesIO()
        inverted.save(img_byte, format="PNG")
        img_byte.seek(0)
        rect = fitz.Rect(0, 0, pix.width, pix.height)
        new_page = new_doc.new_page(width=rect.width, height=rect.height)
        new_page.insert_image(rect, stream=img_byte.read())
    out = io.BytesIO()
    new_doc.save(out)
    out.seek(0)
    doc.close()
    new_doc.close()
    return out

def merge_pdfs(pdf_streams):
    final_doc = fitz.open()
    for stream in pdf_streams:
        src = fitz.open(stream=stream.read(), filetype="pdf")
        final_doc.insert_pdf(src)
        src.close()
    out = io.BytesIO()
    final_doc.save(out)
    out.seek(0)
    final_doc.close()
    return out

def layout_slides_3_per_page(input_stream):
    doc = fitz.open(stream=input_stream.read(), filetype="pdf")
    new_doc = fitz.open()
    page_width = 595
    page_height = 842
    margin_top = 5
    margin_side = 57
    spacing = 0
    slide_width = page_width - margin_side - 5
    available_height = page_height - margin_top - 2 * spacing
    slide_height = available_height / 3
    page_number = 1

    for i in range(0, len(doc), 3):
        page = new_doc.new_page(width=page_width, height=page_height)
        for j in range(3):
            if i + j >= len(doc):
                break
            src_page = doc[i + j]
            pix = src_page.get_pixmap(matrix=fitz.Matrix(1.0, 1.0))
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            img_buffer = io.BytesIO()
            img.save(img_buffer, format="PNG")
            img_buffer.seek(0)
            top = margin_top + j * (slide_height + spacing)
            rect = fitz.Rect(margin_side, top, margin_side + slide_width, top + slide_height)
            page.insert_image(rect, stream=img_buffer.read(), keep_proportion=True)
        text = f"Page {page_number}"
        x = page_width - 100
        y = page_height - 20
        page.insert_text(fitz.Point(x, y), text, fontsize=10, fontname="helv", color=(0, 0, 0))
        page_number += 1

    out = io.BytesIO()
    new_doc.save(out)
    out.seek(0)
    new_doc.close()
    doc.close()
    return out

def zip_pdf(pdf_stream):
    zip_stream = io.BytesIO()
    with zipfile.ZipFile(zip_stream, "w", zipfile.ZIP_DEFLATED) as zipf:
        zipf.writestr("Final_Output.pdf", pdf_stream.getvalue())
    zip_stream.seek(0)
    return zip_stream

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        uploaded_files = request.files.getlist("pdfs")
        inverted_pdfs = []

        for f in uploaded_files:
            inverted = invert_pdf_colors(f.read())
            inverted_pdfs.append(inverted)

        merged_pdf = merge_pdfs(inverted_pdfs)
        final_pdf = layout_slides_3_per_page(merged_pdf)
        zipped = zip_pdf(final_pdf)

        # Store both in memory with unique ID
        file_id = str(uuid.uuid4())
        generated_files[file_id] = {
            "pdf": final_pdf,
            "zip": zipped
        }

        return jsonify({
            "pdf_url": f"/download/pdf/{file_id}",
            "zip_url": f"/download/zip/{file_id}"
        })

    return render_template("index.html")

@app.route("/download/pdf/<file_id>")
def download_pdf(file_id):
    if file_id in generated_files:
        return send_file(
            generated_files[file_id]["pdf"],
            as_attachment=True,
            download_name="converted.pdf",
            mimetype="application/pdf"
        )
    return "PDF not found", 404

@app.route("/download/zip/<file_id>")
def download_zip(file_id):
    if file_id in generated_files:
        return send_file(
            generated_files[file_id]["zip"],
            as_attachment=True,
            download_name="converted.zip",
            mimetype="application/zip"
        )
    return "ZIP not found", 404

if __name__ == "__main__":
    app.run(debug=True)

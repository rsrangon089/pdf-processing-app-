from flask import Flask, request, jsonify, render_template
import io, os, json, fitz
from PIL import Image, ImageOps
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload

app = Flask(__name__)

# Load credentials from environment variable
SCOPES = ['https://www.googleapis.com/auth/drive']
creds_json = os.environ.get("GOOGLE_CREDS")  # Get JSON string from env var
if not creds_json:
    raise Exception("GOOGLE_CREDS environment variable not set")

info = json.loads(creds_json)
credentials = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
drive_service = build('drive', 'v3', credentials=credentials)

# Set your shared folder ID here (put this also in environment if needed)
SHARED_FOLDER_ID = os.environ.get("FOLDER_ID") or "👉তোমার ফোল্ডার আইডি এখানে👈"

# Upload to Drive
def upload_to_drive(name, file_stream, folder_id):
    file_metadata = {'name': name, 'parents': [folder_id]}
    media = MediaIoBaseUpload(file_stream, mimetype='application/pdf')
    file = drive_service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id'
    ).execute()
    return file.get('id')

# Download from Drive
def download_from_drive(file_id):
    request = drive_service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        status, done = downloader.next_chunk()
    fh.seek(0)
    return fh

# Delete from Drive
def delete_from_drive(file_id):
    drive_service.files().delete(fileId=file_id).execute()

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/upload", methods=["POST"])
def upload():
    file = request.files.get('pdf')
    if not file:
        return jsonify({"error": "No file provided"}), 400
    file_stream = io.BytesIO(file.read())
    file_id = upload_to_drive(file.filename, file_stream, SHARED_FOLDER_ID)
    return jsonify({"file_id": file_id})

@app.route("/process", methods=["POST"])
def process():
    data = request.json
    file_id = data.get('file_id')
    if not file_id:
        return jsonify({"error": "file_id required"}), 400

    input_pdf_stream = download_from_drive(file_id)
    doc = fitz.open(stream=input_pdf_stream.read(), filetype="pdf")
    new_doc = fitz.open()
    for page in doc:
        pix = page.get_pixmap()
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        inverted = ImageOps.invert(img)
        img_byte = io.BytesIO()
        inverted.save(img_byte, format="PNG")
        img_byte.seek(0)
        rect = fitz.Rect(0, 0, pix.width, pix.height)
        new_page = new_doc.new_page(width=rect.width, height=rect.height)
        new_page.insert_image(rect, stream=img_byte.read())

    output = io.BytesIO()
    new_doc.save(output)
    output.seek(0)

    processed_file_id = upload_to_drive("processed.pdf", output, SHARED_FOLDER_ID)
    delete_from_drive(file_id)

    download_url = f"https://drive.google.com/uc?id={processed_file_id}&export=download"
    return jsonify({"download_url": download_url})

if __name__ == "__main__":
    app.run(debug=True)

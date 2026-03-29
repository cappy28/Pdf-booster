import os, uuid, subprocess, tempfile, shutil
import fitz  # pymupdf
from PIL import Image
import io
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "/tmp/uploads"
OUTPUT_DIR = "/tmp/outputs"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

A4_W = 595.28
A4_H = 841.89
PT_TO_MM = 25.4 / 72


@app.get("/")
def root():
    return {"status": "ok"}


@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(400, "Fichier PDF requis")

    file_id = str(uuid.uuid4())
    path = os.path.join(UPLOAD_DIR, f"{file_id}.pdf")

    content = await file.read()
    with open(path, "wb") as f:
        f.write(content)

    size_bytes = len(content)
    doc = fitz.open(path)
    pages_info = []
    images_info = []
    non_a4 = 0

    for i, page in enumerate(doc):
        rect = page.rect
        w_mm = round(rect.width  * PT_TO_MM, 1)
        h_mm = round(rect.height * PT_TO_MM, 1)
        is_a4 = abs(rect.width - A4_W) < 5 and abs(rect.height - A4_H) < 5
        if not is_a4:
            non_a4 += 1
        pages_info.append({"page": i+1, "w_mm": w_mm, "h_mm": h_mm, "is_a4": is_a4})

        for img in page.get_images(full=True):
            xref = img[0]
            try:
                base = doc.extract_image(xref)
                pil  = Image.open(io.BytesIO(base["image"]))
                w_px, h_px = pil.size
                dpi_x = w_px / (rect.width  / 72)
                dpi_y = h_px / (rect.height / 72)
                dpi   = round((dpi_x + dpi_y) / 2)
                images_info.append({
                    "page": i+1,
                    "w_px": w_px,
                    "h_px": h_px,
                    "dpi":  dpi,
                    "low_res": dpi < 150
                })
            except Exception:
                continue

    doc.close()

    low_res_count = sum(1 for img in images_info if img["low_res"])
    min_dpi = min((img["dpi"] for img in images_info), default=300)

    score = 100
    recos = []

    if non_a4 > 0:
        score -= 25
        recos.append({"type": "warn", "text": f"{non_a4} page(s) hors format A4"})
    if low_res_count > 0:
        score -= min(30, low_res_count * 5)
        recos.append({"type": "warn", "text": f"{low_res_count} image(s) en basse résolution ({min_dpi} DPI réel) → upscaling nécessaire"})
    if size_bytes > 10 * 1024 * 1024:
        recos.append({"type": "info", "text": f"Fichier lourd ({round(size_bytes/1024/1024,1)} MB) → compression recommandée"})
    if score >= 90:
        recos.append({"type": "ok", "text": "PDF en bon état pour l'impression"})

    return {
        "file_id":       file_id,
        "total_pages":   len(pages_info),
        "size_mb":       round(size_bytes / 1024 / 1024, 2),
        "pages":         pages_info,
        "images":        images_info,
        "non_a4_count":  non_a4,
        "low_res_count": low_res_count,
        "min_dpi":       min_dpi,
        "score":         max(0, score),
        "recommendations": recos,
    }


class OptimizeRequest(BaseModel):
    file_id: str
    convert_a4:      bool = True
    upscale_images:  bool = True
    convert_cmyk:    bool = True


@app.post("/optimize")
def optimize(req: OptimizeRequest):
    src = os.path.join(UPLOAD_DIR, f"{req.file_id}.pdf")
    if not os.path.exists(src):
        raise HTTPException(404, "Fichier non trouvé — re-uploadez le PDF")

    with tempfile.TemporaryDirectory() as tmp:
        current = src
        steps   = []

        # Étape 1 : conversion A4 + rendu 150 DPI (rapide, dans le timeout Render free)
        if req.convert_a4 or req.upscale_images:
            step1 = os.path.join(tmp, "step1.pdf")
            doc_src = fitz.open(current)
            doc_out = fitz.open()

            for page in doc_src:
                rect = page.rect
                # 150 DPI = bon compromis vitesse/qualité sur Render free
                mat = fitz.Matrix(150/72, 150/72)
                pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB, alpha=False)
                img_bytes = pix.tobytes("jpeg", jpg_quality=90)

                if req.convert_a4:
                    new_page = doc_out.new_page(width=A4_W, height=A4_H)
                    margin  = 28.35
                    avail_w = A4_W - 2 * margin
                    avail_h = A4_H - 2 * margin
                    ratio   = min(avail_w / rect.width, avail_h / rect.height)
                    nw = rect.width  * ratio
                    nh = rect.height * ratio
                    x0 = (A4_W - nw) / 2
                    y0 = (A4_H - nh) / 2
                    dest = fitz.Rect(x0, y0, x0+nw, y0+nh)
                else:
                    new_page = doc_out.new_page(width=rect.width, height=rect.height)
                    dest = fitz.Rect(0, 0, rect.width, rect.height)

                new_page.insert_image(dest, stream=img_bytes)

            doc_out.save(step1)
            doc_src.close()
            doc_out.close()
            current = step1

            if req.convert_a4:     steps.append("Conversion A4 avec marges")
            if req.upscale_images: steps.append("Rendu 150 DPI (upscaling réel)")

        # Étape 2 : Ghostscript CMYK + compression
        step2 = os.path.join(tmp, "step2.pdf")
        gs_args = [
            "gs", "-dBATCH", "-dNOPAUSE", "-dQUIET", "-dSAFER",
            "-sDEVICE=pdfwrite",
            "-dCompatibilityLevel=1.4",
            "-dPDFSETTINGS=/ebook",  # plus rapide que /printer
            "-dEmbedAllFonts=true",
        ]
        if req.convert_cmyk:
            gs_args += [
                "-sColorConversionStrategy=CMYK",
                "-dProcessColorModel=/DeviceCMYK",
            ]
        gs_args += [f"-sOutputFile={step2}", current]

        result = subprocess.run(gs_args, capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            current = step2
            if req.convert_cmyk: steps.append("Conversion couleurs CMYK")
            steps.append("Compression Ghostscript")

        out_path = os.path.join(OUTPUT_DIR, f"{req.file_id}_optimized.pdf")
        shutil.copy(current, out_path)

    in_size  = os.path.getsize(src)
    out_size = os.path.getsize(out_path)
    saved    = round((1 - out_size / in_size) * 100)

    return {
        "download_url":  f"/download/{req.file_id}",
        "steps_applied": steps,
        "original_mb":   round(in_size  / 1024 / 1024, 2),
        "optimized_mb":  round(out_size / 1024 / 1024, 2),
        "saved_percent": max(0, saved),
    }


@app.get("/download/{file_id}")
def download(file_id: str):
    path = os.path.join(OUTPUT_DIR, f"{file_id}_optimized.pdf")
    if not os.path.exists(path):
        raise HTTPException(404, "Fichier non trouvé")
    return FileResponse(path, media_type="application/pdf", filename="print-ready.pdf")
    

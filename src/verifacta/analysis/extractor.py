"""Convierte páginas de PDF E14 a imágenes para análisis visual."""
import fitz  # pymupdf
from pathlib import Path


def pdf_to_images(pdf_path: Path, dpi: int = 150) -> list[bytes]:
    """
    Retorna lista de imágenes PNG (una por página) como bytes.
    DPI 150 es suficiente para que Gemini lea los números con claridad.
    """
    pdf = fitz.open(str(pdf_path))
    images = []
    for page in pdf:
        pix = page.get_pixmap(dpi=dpi)
        images.append(pix.tobytes("png"))
    pdf.close()
    return images
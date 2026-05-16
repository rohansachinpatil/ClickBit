"""
utils/ocr.py
-------------
OCR wrapper using pytesseract.
Requires Tesseract binary to be installed on the system.
"""

import pytesseract
from PIL import Image
from utils.logger import get_logger

logger = get_logger(__name__)

# If tesseract is not on PATH, uncomment and set the path:
# pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


def ocr_image(image_path: str) -> str:
    """
    Runs OCR on the image at `image_path`.
    Returns extracted text as a string.
    """
    logger.debug(f"Running OCR on: {image_path}")
    try:
        img = Image.open(image_path)
        text = pytesseract.image_to_string(img)
        logger.info(f"OCR extracted {len(text)} characters")
        return text.strip()
    except Exception as e:
        logger.error(f"OCR failed: {e}")
        return ""


def ocr_pil_image(pil_image: Image.Image) -> str:
    """
    Runs OCR directly on a PIL Image object (no disk I/O).
    Useful when the image is already in memory.
    """
    logger.debug("Running OCR on in-memory PIL image")
    try:
        text = pytesseract.image_to_string(pil_image)
        return text.strip()
    except Exception as e:
        logger.error(f"OCR failed: {e}")
        return ""

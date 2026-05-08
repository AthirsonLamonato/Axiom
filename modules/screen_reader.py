"""
modules/screen_reader.py — Leitura de texto na tela via OCR
Requer: pip install pytesseract Pillow
Tesseract OCR: github.com/UB-Mannheim/tesseract/wiki (Windows)
               sudo apt install tesseract-ocr tesseract-ocr-por (Linux)
"""

import logging
import platform

logger = logging.getLogger(__name__)
OS = platform.system()

_INSTALL_HINT = (
    "Dependências ausentes. Instale:\n"
    "  pip install pytesseract Pillow\n"
    "  Windows: baixe Tesseract em github.com/UB-Mannheim/tesseract/wiki\n"
    "  Linux:   sudo apt install tesseract-ocr tesseract-ocr-por"
)


def _ocr(image) -> str:
    import pytesseract
    # Tenta pt+en; fallback para eng se lang pt não estiver disponível
    try:
        return pytesseract.image_to_string(image, lang="por+eng").strip()
    except Exception:
        return pytesseract.image_to_string(image, lang="eng").strip()


def _grab_screen():
    """Captura a tela inteira. Compatível com Windows e Linux."""
    try:
        from PIL import ImageGrab
        return ImageGrab.grab()
    except Exception:
        import pyautogui
        return pyautogui.screenshot()


def read_screen(*_) -> str:
    """Captura e transcreve o texto visível na tela inteira."""
    try:
        import pytesseract  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError:
        return _INSTALL_HINT

    try:
        img = _grab_screen()
        text = _ocr(img)
        if not text:
            return "Nenhum texto detectado na tela."
        if len(text) > 1000:
            text = text[:1000] + "\n... (truncado — use 'lê a janela' para foco)"
        return f"Texto detectado na tela:\n{text}"
    except Exception as e:
        logger.error("Erro no OCR da tela: %s", e, exc_info=True)
        return f"Erro ao ler a tela: {e}"


def read_region(*_) -> str:
    """Captura uma região de 800×600 px centralizada na tela (foco na área principal)."""
    try:
        import pytesseract  # noqa: F401
        from PIL import ImageGrab
        import pyautogui
    except ImportError:
        return _INSTALL_HINT

    try:
        sw, sh = pyautogui.size()
        w, h = min(800, sw), min(600, sh)
        x0, y0 = (sw - w) // 2, (sh - h) // 2
        img = ImageGrab.grab(bbox=(x0, y0, x0 + w, y0 + h))
        text = _ocr(img)
        if not text:
            return "Nenhum texto detectado na região central."
        if len(text) > 800:
            text = text[:800] + "\n... (truncado)"
        return f"Texto na região central:\n{text}"
    except Exception as e:
        return f"Erro ao ler a região: {e}"


def save_screenshot(*_) -> str:
    """Salva um screenshot em data/screenshots/."""
    import os
    from datetime import datetime
    try:
        img = _grab_screen()
    except ImportError:
        return _INSTALL_HINT
    except Exception as e:
        return f"Erro ao capturar tela: {e}"

    out_dir = "data/screenshots"
    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(out_dir, f"screenshot_{ts}.png")
    img.save(path)
    return f"Screenshot salvo em {path}."

"""Server-side signature image processing pipeline.

Accept a JPEG or PNG upload, remove the background using OpenCV thresholding
and morphological cleanup, crop tightly to the ink bounding box, and return
the result as a transparent PNG byte string.

All output is PNG with an alpha channel regardless of input format.
"""

from __future__ import annotations

import io

import cv2
import numpy as np
from PIL import Image


class SignatureProcessor:
    """Clean a scanned/photographed signature and return a transparent PNG.

    Designed for signatures written in dark ink on a light background.
    Uses Otsu's automatic thresholding as the primary path; falls back to
    adaptive thresholding when the image has uneven lighting. A quality gate
    rejects images where too few ink pixels survive the cleanup step.
    """

    _PADDING_PX: int = 4
    # Fraction of total pixels that must be ink after cleanup.
    _MIN_INK_RATIO: float = 0.002

    @classmethod
    def process(cls, image_bytes: bytes, content_type: str) -> bytes:
        """Remove background, crop, and return transparent PNG bytes.

        :param image_bytes: Raw bytes of a JPEG or PNG file.
        :param content_type: MIME type hint (``image/png`` or ``image/jpeg``).
        :return: PNG-encoded bytes with transparent background.
        :raises ValueError: If the image cannot be decoded or no ink is detected.
        """
        arr = np.frombuffer(image_bytes, dtype=np.uint8)
        bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if bgr is None:
            raise ValueError("Bild konnte nicht geladen werden.")

        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

        # Primary path: Otsu's method selects threshold automatically from the
        # image histogram — robust for clean scans with bimodal intensity.
        _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        # Fallback: adaptive thresholding handles uneven lighting / shadows.
        if cls._ink_ratio(mask) < cls._MIN_INK_RATIO:
            mask = cv2.adaptiveThreshold(
                gray, 255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY_INV,
                blockSize=15,
                C=10,
            )

        # Morphological cleanup: OPEN removes isolated dust/speckles;
        # CLOSE fills small gaps within ink strokes.
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

        if cls._ink_ratio(mask) < cls._MIN_INK_RATIO:
            raise ValueError(
                "Signatur konnte nicht erkannt werden. "
                "Bitte eine dunkle Unterschrift auf weißem Papier, "
                "gut ausgeleuchtet und scharf, hochladen."
            )

        # Crop to ink bounding box plus small padding.
        cropped_bgr, cropped_mask = cls._crop_to_bounding_box(bgr, mask)

        return cls._to_transparent_png(cropped_bgr, cropped_mask)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _ink_ratio(mask: np.ndarray) -> float:
        """Return the fraction of pixels set in the binary mask."""
        return float(mask.sum()) / 255.0 / mask.size

    @classmethod
    def _crop_to_bounding_box(
        cls, bgr: np.ndarray, mask: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        """Crop both arrays to the tight bounding box of non-zero mask pixels.

        :param bgr: Original BGR image.
        :param mask: Binary ink mask (ink=255, background=0).
        :return: Tuple of (cropped BGR, cropped mask).
        """
        coords = cv2.findNonZero(mask)
        if coords is None:
            return bgr, mask
        x, y, w, h = cv2.boundingRect(coords)
        pad = cls._PADDING_PX
        h_img, w_img = bgr.shape[:2]
        x0 = max(0, x - pad)
        y0 = max(0, y - pad)
        x1 = min(w_img, x + w + pad)
        y1 = min(h_img, y + h + pad)
        return bgr[y0:y1, x0:x1], mask[y0:y1, x0:x1]

    @staticmethod
    def _to_transparent_png(bgr: np.ndarray, mask: np.ndarray) -> bytes:
        """Convert a BGR crop and its ink mask to a transparent PNG byte string.

        Ink pixels (mask=255) are fully opaque; background pixels (mask=0) are
        fully transparent. The original ink colour is preserved.

        :param bgr: Cropped BGR image.
        :param mask: Corresponding binary ink mask.
        :return: PNG-encoded bytes with an alpha channel.
        """
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb).convert("RGBA")
        alpha = Image.fromarray(mask, mode="L")
        pil_img.putalpha(alpha)
        buf = io.BytesIO()
        pil_img.save(buf, format="PNG")
        return buf.getvalue()

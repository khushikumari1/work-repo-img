"""
local_processor.py
──────────────────
Drop-in replacement for lambda_function.py.

Instead of being triggered by an S3 event, this module exposes a single
callable — process_image_locally() — that the main pipeline calls directly
with a local image path and its matching caption text.

No AWS credentials, no boto3, no S3 buckets, no Lambda handler needed.
"""

import os
import json
import sys
import logging

# ─── Ensure repo root is on sys.path so `config` is importable ───────────────
_REPO_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from config import JSON_OUTPUT_DIR
from gemini_AI_Model import GeminiImageProcessor

logger = logging.getLogger(__name__)

# ─── Module-level singleton — built once, reused for every image ──────────────
# This mirrors the Lambda pattern where the processor is initialised outside
# the handler so it is reused across warm invocations.
_processor: GeminiImageProcessor | None = None


def _get_processor() -> GeminiImageProcessor:
    """Return the shared GeminiImageProcessor, creating it on first call."""
    global _processor
    if _processor is None:
        logger.info("Initialising GeminiImageProcessor (first call)...")
        _processor = GeminiImageProcessor()
        logger.info("GeminiImageProcessor ready.")
    return _processor


def process_image_locally(image_path: str, caption: str) -> dict:
    """
    Process a single image + caption through Gemini and persist the result
    as a JSON file under JSON_OUTPUT_DIR.

    Parameters
    ----------
    image_path : str
        Absolute path to the .jpg (or .png / .bmp / .tiff) image file.
    caption : str
        Figure caption extracted from the manuscript DOCX.  Pass an empty
        string if no caption is available.

    Returns
    -------
    dict
        The result dict produced by GeminiImageProcessor.process_image().
        Keys include: Image_complexity, short_alt_text, long_alt_text,
        Confidence_Score, Relevance_Score, Correctness_Score, Accuracy_Score.
        On failure returns {"Error": "Image not processed"}.

    Side-effects
    ------------
    Writes <base_name>.json to JSON_OUTPUT_DIR so the caller can read it
    back just as it would have read the file downloaded from S3.
    """
    image_path = os.path.normpath(image_path)

    if not os.path.exists(image_path):
        logger.error(f"Image not found: {image_path}")
        return {"Error": "Image not processed"}

    base_name = os.path.splitext(os.path.basename(image_path))[0]
    json_path = os.path.join(JSON_OUTPUT_DIR, f"{base_name}.json")

    logger.info(f"Processing image: {os.path.basename(image_path)}")

    try:
        processor = _get_processor()
        result_dict = processor.process_image(image_path, caption)

        if not isinstance(result_dict, dict):
            raise ValueError(
                f"process_image must return a dict, got {type(result_dict)}"
            )

        # ── Persist JSON locally (mirrors the S3 upload in the old Lambda) ──
        os.makedirs(JSON_OUTPUT_DIR, exist_ok=True)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(result_dict, f, indent=2, ensure_ascii=False)

        logger.info(f"Result written: {json_path}")
        return result_dict

    except Exception as e:
        logger.exception(f"Failed to process {os.path.basename(image_path)}: {e}")
        return {"Error": "Image not processed"}


def get_json_path(image_path: str) -> str:
    """
    Return the expected local JSON output path for a given image path.
    Useful for the caller to check whether a result already exists.
    """
    base_name = os.path.splitext(os.path.basename(image_path))[0]
    return os.path.join(JSON_OUTPUT_DIR, f"{base_name}.json")

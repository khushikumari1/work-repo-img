"""
config.py — Central configuration for the Frontlist alt-text pipeline.

Edit ONLY this file to adapt the pipeline to your environment.
Every other script imports its settings from here — no hardcoded paths
or credentials anywhere else.
"""

import os

# ─── Root directory of this repository ───────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ══════════════════════════════════════════════════════════════════════════════
# EXECUTION MODE
# ═════════════════════════════════════════════════════════════════════════════
# "local" → Gemini is called directly on this machine. No AWS needed.
# "s3"    → Images are uploaded to S3, Lambda processes them, results are
#            polled back from S3. Requires valid AWS credentials below.
EXECUTION_MODE = "local"   # <── change to "s3" to switch back to AWS mode

# ══════════════════════════════════════════════════════════════════════════════
# WATCHDOG SETTINGS
# ══════════════════════════════════════════════════════════════════════════════
# Network share folder that watchdog monitors for new book-batch folders.
WATCH_DIRECTORY = os.path.join(BASE_DIR, "INPUTs")

# Folder where processed output is written.
OUT_BASE_DIRECTORY = os.path.join(BASE_DIR, "OUTPUTs")

# Seconds to wait after a new folder is detected before copying + processing,
# to allow the remote file transfer to finish writing all files first.
WAIT_SECONDS = 300

# ─── GCP / Gemini ─────────────────────────────────────────────────────────────
# Path to the Google Cloud service-account JSON key file.
# The file lives at the repo root on this machine.
SERVICE_ACCOUNT_FILE = os.path.join(BASE_DIR, "rs-translations-f5dd75a355f5.json")

# Gemini model to use (must support vision).
GEMINI_MODEL = "gemini-3.1-flash-image"
GCP_LOCATION = "global"

# ─── AWS / S3 settings (used only when EXECUTION_MODE = "s3") ─────────────────
AWS_ACCESS_KEY_ID     = os.getenv("AWS_ACCESS_KEY_ID",     "AKIA2CSGOMFSU2ETQBGU")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "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")
AWS_REGION            = "us-east-1"
S3_BUCKET             = "elsevier-idtf-generation"

# S3 key prefixes (must match the Lambda trigger filter in template.yaml)
S3_IMAGE_PREFIX  = "gemini-In/"
S3_TEXT_PREFIX   = "gemini-txt/"
S3_OUTPUT_PREFIX = "gemini-Out/"

# How long to wait for Lambda to produce the result JSON.
# max_attempts × wait_seconds = total timeout per image (default: 60 s)
S3_POLL_MAX_ATTEMPTS = 12
S3_POLL_WAIT_SECONDS = 5

# ─── Local working folders ────────────────────────────────────────────────────
# Temporary folder where extracted images and caption .txt files are staged.
TEMP_IMAGES_DIR = os.path.join(BASE_DIR, "workspace", "extracted_img")

# Folder where Gemini JSON result files land (local mode) or are downloaded
# to (S3 mode).
JSON_OUTPUT_DIR = os.path.join(BASE_DIR, "workspace", "output_json")

# Log file written by GeminiImageProcessor.
LOG_FILE = os.path.join(BASE_DIR, "workspace", "gemini_logs.txt")

# Debug output folder used by pdf_image_extractor when DEBUG = True.
DEBUG_FOLDER = os.path.join(BASE_DIR, "DEBUG")

# Path to the Excel column-template file (must exist at repo root).
TEMPLATE_EXCEL = os.path.join(BASE_DIR, "fm_rm_alt_text.xlsx")

# ─── Pipeline behaviour ───────────────────────────────────────────────────────
# Number of parallel threads (Gemini calls in local mode; S3 uploads in S3 mode).
MAX_WORKERS = 6

# ─── Workspace auto-creation ─────────────────────────────────────────────────
# Directories are created at import time so nothing else needs to check.
for _d in (TEMP_IMAGES_DIR, JSON_OUTPUT_DIR, os.path.dirname(LOG_FILE), DEBUG_FOLDER, OUT_BASE_DIRECTORY):
    os.makedirs(_d, exist_ok=True)
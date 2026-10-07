# Frontlist Alt-Text Pipeline

Automated accessibility alt-text generation for scientific/medical figures in academic textbooks.

The pipeline watches a network share for incoming book-batch folders, extracts figures from per-chapter PDF + DOCX + Excel bundles, sends each figure to Google Gemini, and writes structured short and long alt-text descriptions into a formatted Excel output file.

Two execution modes are supported and switchable with **one line in `config.py`**:

| Mode | How it works |
|---|---|
| `"local"` | Gemini is called directly on this machine. No AWS needed. |
| `"s3"` | Images upload to S3, AWS Lambda processes them, results are polled back. Original cloud workflow. |

---

## Repository Layout

```
C:\Users\MAC014904\Desktop\Frontlist\
├── config.py                          ← ALL settings live here — edit this file only
├── frontlist_script.py                ← Main pipeline orchestrator
├── watch_dog.py                       ← Network-share folder watcher
├── pdf_image_extractor.py             ← PDF → PIL.Image extraction
├── fm_rm_alt_text.xlsx                ← Output column template  (required)
├── rs-translations-f5dd75a355f5.json  ← GCP service account key (required)
├── requirements.txt
├── README.md
├── DEBUG\                             ← Debug images (written when DEBUG=True)
├── INPUTs\                            ← Local test input folders
├── workspace\
│   ├── extracted_img\                 ← Temp staging for images + captions
│   ├── output_json\                   ← Gemini result JSONs
│   └── gemini_logs.txt                ← Per-call Gemini log
└── gemini-alt-text-generation\
    └── src\
        ├── gemini_AI_Model.py         ← GeminiImageProcessor (LangChain + Gemini)
        ├── local_processor.py         ← Local entry point (replaces Lambda)
        └── lambda_function.py         ← AWS Lambda handler (s3 mode)
```

---

## How It Works  

```
Network share:  \\192.168.60.25\Downloads\Frontlist\Input_April
                └── <NewBookFolder>/          ← watchdog detects this
                    └── <ChapterFolder>/
                        ├── CH####_*_ArtPDF.pdf
                        ├── CH####_*_Clean.docx
                        └── CH####_*_ArtLog.xlsx

          │  watch_dog.py
          │  1. Detects new folder on share
          │  2. Waits WAIT_SECONDS (300s) for transfer to finish
          │  3. Copies folder → \\192.168.60.25\Downloads\Frontlist\Output_April\
          │  4. Calls generate_IDTF_first_step() on each chapter sub-folder
          ▼

          frontlist_script.py  (per chapter folder)
          1. Validate ArtLog Excel  →  extract figure ID list
          2. Accept tracked changes in DOCX (Word COM)  →  extract captions
          3. Extract images from ArtPDF  →  list of (fig_key, PIL.Image)
          4. Save each figure as .jpg + caption .txt  →  workspace\extracted_img\

          ├─── EXECUTION_MODE = "local" ──────────────────────────────────────
          │    Parallel threads → GeminiImageProcessor.process_image()
          │    Results written to workspace\output_json\
          │
          └─── EXECUTION_MODE = "s3" ─────────────────────────────────────────
               Upload .txt → S3 gemini-txt/
               Upload .jpg → S3 gemini-In/   (triggers Lambda)
               Poll S3 gemini-Out/ for result JSON  (12 × 5s = 60s max)
               Download JSON → workspace\output_json\
               Delete S3 objects after download

          │  (both modes rejoin here)
          ▼
          5. Parse JSON  →  fill output DataFrame
          6. Save CH####_*_ArtLog_with_img.xlsx  (alt text + thumbnails)
          7. Append to FRONTLIST-IDTF.xlsx  (running log)
             S3 mode also uploads FRONTLIST-IDTF.xlsx to S3
          8. Clean up temp files
```

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. GCP service account key

Place `rs-translations-f5dd75a355f5.json` in the **repo root**:

```
C:\Users\MAC014904\Desktop\Frontlist\rs-translations-f5dd75a355f5.json
```

The service account needs the **Vertex AI User** role (`roles/aiplatform.user`) on the GCP project.

### 3. Column-template Excel

Place `fm_rm_alt_text.xlsx` in the **repo root**. This defines the output spreadsheet column structure.

### 4. Review `config.py`

Open `config.py` — all settings are in one place:

| Setting | Current value | Description |
|---|---|---|
| `EXECUTION_MODE` | `"local"` | `"local"` or `"s3"` |
| `WATCH_DIRECTORY` | `\\192.168.60.25\Downloads\Frontlist\Input_April` | Folder watchdog monitors |
| `OUT_BASE_DIRECTORY` | `\\192.168.60.25\Downloads\Frontlist\Output_April` | Output destination |
| `WAIT_SECONDS` | `300` | Wait before copying (seconds) |
| `SERVICE_ACCOUNT_FILE` | `rs-translations-f5dd75a355f5.json` (repo root) | GCP key |
| `GEMINI_MODEL` | `gemini-3.1-flash-image` | Gemini model |
| `GCP_LOCATION` | `global` | Vertex AI region |
| `AWS_ACCESS_KEY_ID` | env var / fallback | AWS key (s3 mode) |
| `AWS_SECRET_ACCESS_KEY` | env var / fallback | AWS secret (s3 mode) |
| `S3_BUCKET` | `elsevier-idtf-generation` | S3 bucket (s3 mode) |
| `S3_POLL_MAX_ATTEMPTS` | `12` | Max S3 polls per image |
| `S3_POLL_WAIT_SECONDS` | `5` | Seconds between polls |
| `MAX_WORKERS` | `6` | Parallel threads |
| `DEBUG_FOLDER` | `DEBUG\` (repo root) | Debug images output |

---

## Switching Execution Mode

Edit the single line in `config.py`:

```python
EXECUTION_MODE = "local"   # call Gemini directly — no AWS
EXECUTION_MODE = "s3"      # upload to S3, Lambda processes, poll results back
```

---

## Running

### Watchdog (production — monitors network share)

```bash
python watch_dog.py
```

Watches `\\192.168.60.25\Downloads\Frontlist\Input_April`.  
Copies new folders to `\\192.168.60.25\Downloads\Frontlist\Output_April` and processes them automatically.  
Stop with `Ctrl+C`.

### Direct run (testing — process a local folder)

```bash
# Process all chapter folders under INPUTs\
python frontlist_script.py

# Process a specific folder
python frontlist_script.py "C:\Users\MAC014904\Desktop\Frontlist\INPUTs\Carlson_9780443281594_B4"
```

---

## Outputs

| File | Location | Description |
|---|---|---|
| `CH####_*_ArtLog_with_img.xlsx` | Next to source ArtLog | Alt text + embedded figure thumbnails |
| `images\*.jpg` | Inside each chapter folder | Extracted figures by figure ID |
| `FRONTLIST-IDTF.xlsx` | Repo root | Running log appended across all chapters |
| `workspace\gemini_logs.txt` | Repo root | Per-call Gemini response log |

---

## Troubleshooting

**`FileNotFoundError: fm_rm_alt_text.xlsx`**  
Place the template Excel at `C:\Users\MAC014904\Desktop\Frontlist\fm_rm_alt_text.xlsx`.

**`FileNotFoundError: rs-translations-f5dd75a355f5.json`**  
Place the GCP key at `C:\Users\MAC014904\Desktop\Frontlist\rs-translations-f5dd75a355f5.json`.

**`ModuleNotFoundError: pdf_image_extractor`**  
Run the script from the repo root, or ensure `C:\Users\MAC014904\Desktop\Frontlist` is on `PYTHONPATH`.

**`Failed to start Word COM`**  
Microsoft Word must be installed. The script uses Win32 COM to accept tracked changes in DOCX files.

**`google.auth.exceptions.DefaultCredentialsError`**  
The service account JSON is missing or corrupted.

**Gemini rate limit errors (local mode)**  
Reduce `MAX_WORKERS` in `config.py` (e.g. `2`) to lower concurrent request rate.

**S3 JSON timeout (s3 mode)**  
Increase `S3_POLL_MAX_ATTEMPTS` or `S3_POLL_WAIT_SECONDS` in `config.py`. Check Lambda logs in CloudWatch for errors.

**Watchdog does not detect new folders**  
Ensure the network share `\\192.168.60.25\Downloads\Frontlist\Input_April` is mounted and accessible. Watchdog requires the path to be reachable at startup.

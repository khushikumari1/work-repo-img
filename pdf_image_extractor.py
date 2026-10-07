
# pdf_image_extractor.py - Integrated with your existing workflow
import os
import sys
import pymupdf as fitz  # PyMuPDF (replaces `import fitz` — deprecated in 1.25+)
import cv2
import numpy as np
import re
from datetime import datetime
from collections import Counter
from PIL import Image
from collections import OrderedDict

# ─── Import DEBUG_FOLDER from central config ─────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
from config import DEBUG_FOLDER

# Rendering scale (used both for rendering pixels and for scaling text coords)
RENDER_SCALE = 2.0

# Debug mode — set to True to save intermediate images to DEBUG_FOLDER.
DEBUG = True

if DEBUG:
    os.makedirs(DEBUG_FOLDER, exist_ok=True)

# ─────────────────────────────────────────────────────────────────────────────
# Hardcoded caption block keywords
# ─────────────────────────────────────────────────────────────────────────────
CAPTION_BLOCK_KEYWORDS = [
    "Job:",
    "Chapter:",
    "Batch:",
    "Fig:",
    "Size:",
    "Image",
    "Placed",
    "Desktop",
    "Images",
    "Color",
]


# ------------------------
# Render PDF pages to images
# ------------------------
def render_pdf_pages_to_images(doc, scale=RENDER_SCALE):
    rendered = {}
    m = fitz.Matrix(scale, scale)
    for i, page in enumerate(doc):
        pix = page.get_pixmap(matrix=m, alpha=False)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
        if pix.n == 3:
            img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
        rendered[i + 1] = (img, scale)
    return rendered


# ------------------------
# Extract text from PDF page
# ------------------------
def extract_text_from_page(doc, page_num):
    page = doc[page_num - 1]
    words = page.get_text("words")
    text_data = []
    for item in words:
        if len(item) >= 5:
            x0, y0, x1, y1, word = item[0], item[1], item[2], item[3], item[4]
            word = re.sub(r'[\s\u00a0\u2002\u2003\u2009]+', '', word).strip()
            if word:
                text_data.append((word, (x0, y0, x1, y1)))
    return text_data


# ------------------------
# Caption text detection
# ------------------------
def is_caption_text_pattern(text_data, page_height_pdf_pts, scale_factor=RENDER_SCALE):
    caption_patterns = [
        r'f\d+-\d+-\d+', r'u\d+-\d+-\d+', r'[Ff]igure\s*\d+',
        r'[Ff]ig:?\s*[\w\d]', r'[Tt]able\s+\d+', r'\.jpg$', r'\.png$', r'\.eps$',
        r'Job:\s*[\w-]+', r'Chapter:\s*[\w\d]+', r'Batch:\s*\d+',
        r'Image\s+(PPI|Type|Modified)'
    ]

    bottom_threshold_pdf = page_height_pdf_pts * 0.70
    caption_bbox_list = []

    for word, (x0, y0, x1, y1) in text_data:
        if y0 > bottom_threshold_pdf:
            for pattern in caption_patterns:
                if re.search(pattern, word, re.IGNORECASE):
                    caption_bbox_list.append((
                        x0 * scale_factor, y0 * scale_factor,
                        x1 * scale_factor, y1 * scale_factor
                    ))
                    break

    if caption_bbox_list:
        x0_min = min(b[0] for b in caption_bbox_list)
        y0_min = min(b[1] for b in caption_bbox_list)
        x1_max = max(b[2] for b in caption_bbox_list)
        y1_max = max(b[3] for b in caption_bbox_list)
        return True, (int(x0_min), int(y0_min), int(x1_max), int(y1_max))

    return False, None


# ------------------------
# Find captions near images
# ------------------------
def find_near_image_captions(text_data, image_boxes, page_height_pdf_pts,
                             scale_factor=RENDER_SCALE, proximity_px=80):
    caption_keywords = [
        "Job:", "Fig:", "Figure", "Batch:", "Chapter:", "Image PPI",
        "Image Type", "Image Modified", "Color Space", "Desktop Code",
        "Placed Image", "Size:", "PPI:", "Image", "EPS"
    ]

    caption_boxes = []
    for word, (x0, y0, x1, y1) in text_data:
        if any(kw.lower() in word.lower() for kw in caption_keywords):
            sx0 = int(x0 * scale_factor)
            sy0 = int(y0 * scale_factor)
            sx1 = int(x1 * scale_factor)
            sy1 = int(y1 * scale_factor)

            for bx, by, bw, bh in image_boxes:
                bx1, by1 = bx + bw, by + bh
                if sy0 >= by1 and (sy0 - by1) <= proximity_px:
                    caption_boxes.append((sx0, sy0, sx1, sy1))
                    break
                if sy0 <= by1 and sy1 >= by:
                    caption_boxes.append((sx0, sy0, sx1, sy1))
                    break

    if not caption_boxes:
        return None

    x0 = min(b[0] for b in caption_boxes)
    y0 = min(b[1] for b in caption_boxes)
    x1 = max(b[2] for b in caption_boxes)
    y1 = max(b[3] for b in caption_boxes)

    return (int(x0), int(y0), int(x1), int(y1))


# ------------------------
# Detect content regions using morphology
# ─────────────────────────────────────────────────────────────────────────────
def detect_content_regions(img, caption_cut_y=None):

    if caption_cut_y is not None and caption_cut_y > 0:
        working = img[:caption_cut_y, :]
    else:
        working = img

    gray = cv2.cvtColor(working, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 240, 255, cv2.THRESH_BINARY_INV)

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (12, 12))
    closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=1)

    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    boxes = []
    for contour in contours:
        area = cv2.contourArea(contour)
        x, y, w, h = cv2.boundingRect(contour)
        if (area > 2000 and w > 40 and h > 40) or (area > 800 and w > 25 and h > 25):
            boxes.append((x, y, w, h))

    return boxes


# ------------------------
# Geometry helpers
# ------------------------
def box_contains_caption_text(box, caption_bbox):
    if caption_bbox is None:
        return False
    bx, by, bw, bh = box
    cx0, cy0, cx1, cy1 = caption_bbox
    box_center_y = by + bh / 2
    if box_center_y < cy0:
        return False
    if bx + bw < cx0 or bx > cx1:
        return False
    return True


def create_unified_bbox(boxes):
    if not boxes:
        return None
    x_min = min(box[0] for box in boxes)
    y_min = min(box[1] for box in boxes)
    x_max = max(box[0] + box[2] for box in boxes)
    y_max = max(box[1] + box[3] for box in boxes)
    return (x_min, y_min, x_max - x_min, y_max - y_min)


def is_isolated_bottom_caption(box, all_boxes, page_height_px, page_width_px):
    x, y, w, h = box
    if y < page_height_px * 0.85:
        return False

    aspect_ratio = (w / h) if h > 0 else 0
    width_ratio = w / page_width_px
    height_ratio = h / page_height_px

    is_multiline = (width_ratio > 0.25 and height_ratio < 0.28 and aspect_ratio > 2.5)
    is_singleline = (width_ratio > 0.35 and height_ratio < 0.10 and aspect_ratio > 5)

    if not (is_multiline or is_singleline):
        return False

    box_top = y
    nearest_gap = page_height_px

    for other_box in all_boxes:
        if other_box == box:
            continue
        ox, oy, ow, oh = other_box
        other_bottom = oy + oh
        if other_bottom <= box_top:
            gap = box_top - other_bottom
            nearest_gap = min(nearest_gap, gap)

    return nearest_gap > page_height_px * 0.03


# ------------------------
# Remove bottom caption text (for normal images)
# ------------------------
def remove_bottom_caption_text(crop):
    crop_h, crop_w = crop.shape[:2]
    bottom_start = int(crop_h * 0.90)

    if bottom_start >= crop_h - 5:
        return crop

    bottom = crop[bottom_start:, :].copy()
    gray = cv2.cvtColor(bottom, cv2.COLOR_BGR2GRAY)

    _, dark_mask = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)
    _, light_mask = cv2.threshold(gray, 80, 255, cv2.THRESH_BINARY)
    light_mask = 255 - light_mask
    combined_mask = cv2.bitwise_or(dark_mask, light_mask)

    kernel_h = cv2.getStructuringElement(cv2.MORPH_RECT, (8, 2))
    connected = cv2.morphologyEx(combined_mask, cv2.MORPH_CLOSE, kernel_h, iterations=1)
    contours, _ = cv2.findContours(connected, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        return crop

    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        aspect = (w / h) if h > 0 else 0
        area = cv2.contourArea(c)

        if area > 0.2 * bottom.shape[0] * bottom.shape[1]:
            continue

        if aspect > 4 and w > bottom.shape[1] * 0.25 and h < bottom.shape[0] * 0.5:
            patch = gray[y:y + h, x:x + w]
            if np.var(patch) < 150:
                mask = np.zeros_like(gray)
                cv2.rectangle(mask, (x, y), (x + w, y + h), 255, -1)
                mask = cv2.GaussianBlur(mask, (7, 7), 0)
                bottom = np.where(
                    mask[..., None] > 180,
                    cv2.addWeighted(bottom, 0.6,
                                    np.full_like(bottom, 255, dtype=np.uint8), 0.4, 0),
                    bottom
                )

    crop[bottom_start:, :] = bottom
    return crop


# ------------------------
# Trim white borders
# ------------------------
def trim_white_border(crop, margin=2):
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    _, mask = cv2.threshold(gray, 250, 255, cv2.THRESH_BINARY)
    inv = 255 - mask
    coords = cv2.findNonZero(inv)

    if coords is None:
        return crop

    x, y, w, h = cv2.boundingRect(coords)
    x = max(0, x - margin)
    y = max(0, y - margin)
    w = min(crop.shape[1] - x, w + 2 * margin)
    h = min(crop.shape[0] - y, h + 2 * margin)

    return crop[y:y + h, x:x + w]


# ─────────────────────────────────────────────────────────────────────────────
# Find caption block top Y using HARDCODED keywords from text_data
# ─────────────────────────────────────────────────────────────────────────────
def find_caption_top_y_by_keywords(text_data, page_height_pdf_pts,
                                    scale_factor=RENDER_SCALE):
    bottom_threshold_pdf = page_height_pdf_pts * 0.20
    candidate_y_pixels = []

    for word, (x0, y0, x1, y1) in text_data:
        if y0 < bottom_threshold_pdf:
            continue

        clean_word = re.sub(r'[\s\u00a0\u2002\u2003\u2009\u200b]+', '', word).strip()

        for kw in CAPTION_BLOCK_KEYWORDS:
            if clean_word.lower().startswith(kw.lower()):
                y_pixel = int(y0 * scale_factor)
                candidate_y_pixels.append(y_pixel)
                break

    if not candidate_y_pixels:
        return None

    top_y = min(candidate_y_pixels) - 15
    return max(0, top_y)


# ─────────────────────────────────────────────────────────────────────────────
# Blank caption block for tiny images using hardcoded keyword positions
# ─────────────────────────────────────────────────────────────────────────────
def blank_caption_for_tiny_image(img, text_data, page_height_pdf_pts, scale_factor):
    page_h, page_w = img.shape[:2]

    caption_top_y = find_caption_top_y_by_keywords(
        text_data, page_height_pdf_pts, scale_factor
    )
    if caption_top_y is None:
        caption_top_y = int(page_h * 0.70)
        print(f"[TINY] Keyword not found — fallback at {caption_top_y}")
    else:
        print(f"[TINY] Caption detected at Y={caption_top_y}")

    cleaned = img.copy()
    cleaned[caption_top_y:, :] = 255

    # White-out individual caption keyword words that sit above the cut line
    for word, (x0, y0, x1, y1) in text_data:
        clean_word = re.sub(r'[\s\u00a0\u2002\u2003\u2009\u200b]+', '', word).strip()
        for kw in CAPTION_BLOCK_KEYWORDS:
            if clean_word.lower().startswith(kw.lower()):
                px0 = max(0, int(x0 * scale_factor) - 4)
                py0 = max(0, int(y0 * scale_factor) - 4)
                px1 = min(page_w, int(x1 * scale_factor) + 4)
                py1 = min(page_h, int(y1 * scale_factor) + 4)
                cleaned[py0:py1, px0:px1] = 255
                break

    cleaned = trim_white_border(cleaned)
    return cleaned


# -----------------------
# Separate content and captions
# -----------------------
def separate_content_and_captions(img, boxes, caption_bbox=None):
    if not boxes:
        return [], []

    page_h, page_w = img.shape[:2]
    main_content = []
    captions = []

    for box in boxes:
        if caption_bbox and box_contains_caption_text(box, caption_bbox):
            captions.append(box)
            continue
        if is_isolated_bottom_caption(box, boxes, page_h, page_w):
            captions.append(box)
            continue
        main_content.append(box)

    return main_content, captions


# ─────────────────────────────────────────────────────────────────────────────
# Extract and process image from page
# ─────────────────────────────────────────────────────────────────────────────
def extract_image_from_page(
        img,
        boxes,
        caption_bbox=None,
        text_data=None,
        page_height_pdf_pts=None,
        scale_factor=RENDER_SCALE
):

    page_h, page_w = img.shape[:2]

    # ============================================================
    # STEP 1 — SPLIT CONTENT VS CAPTION BOXES FIRST
    # ============================================================

    main_content, captions = separate_content_and_captions(
        img,
        boxes,
        caption_bbox
    )

    # ============================================================
    # STEP 2 — DECIDE TINY IMAGE PAGE (DETERMINISTIC)
    # ============================================================

    is_tiny_page = False

    if not boxes:
        is_tiny_page = True

    elif caption_bbox is not None:

        large_content_found = False

        for (x, y, w, h) in main_content:

            height_ratio = h / page_h
            area_ratio = (w * h) / (page_h * page_w)

            if (
                height_ratio > 0.25
                or area_ratio > 0.06
            ):
                large_content_found = True
                break

        # ALSO check total unified content size
        unified = create_unified_bbox(main_content)

        if unified is not None:

            ux, uy, uw, uh = unified
            unified_height_ratio = uh / page_h

            if unified_height_ratio < 0.18 and (uw * uh) / (page_h * page_w) < 0.04:
                is_tiny_page = True

        if not large_content_found:
            is_tiny_page = True

    # ============================================================
    # PATH 1 — TINY IMAGE
    # ============================================================

    if is_tiny_page:

        print("  [TINY] Caption-only page detected")

        if text_data is not None and page_height_pdf_pts is not None:

            cleaned = blank_caption_for_tiny_image(
                img,
                text_data,
                page_height_pdf_pts,
                scale_factor
            )

        else:

            cleaned = img.copy()
            cleaned[int(page_h * 0.70):, :] = 255

        cleaned = trim_white_border(cleaned)

        if cleaned.shape[0] < 10 or cleaned.shape[1] < 10:
            return None

        crop_rgb = cv2.cvtColor(cleaned, cv2.COLOR_BGR2RGB)

        return Image.fromarray(crop_rgb)

    # ============================================================
    # PATH 2 — NORMAL IMAGE
    # ============================================================

    if not main_content:
        main_content = boxes

    unified = create_unified_bbox(main_content)

    if unified is None:
        return None

    x, y, w, h = unified

    # ── CLAMP bbox bottom to caption_top_y before any crop ──
    caption_top_y_px = None
    if text_data is not None and page_height_pdf_pts is not None:
        caption_top_y_px = find_caption_top_y_by_keywords(
            text_data, page_height_pdf_pts, scale_factor
        )
    if caption_top_y_px is not None and caption_top_y_px > y:
        clamped_h = caption_top_y_px - y - 5
        if clamped_h > 30:
            print(f"  [CLAMP] bbox bottom clamped {y+h} → {caption_top_y_px}")
            h = clamped_h

    if caption_bbox is not None:

        cx0, cy0, cx1, cy1 = caption_bbox

        caption_bottom_ratio = cy0 / page_h

        image_height_ratio = h / page_h

        # Only cut if caption is clearly bottom metadata
        if (
            caption_bottom_ratio > 0.70      # bottom region
            and image_height_ratio > 0.25    # real image present
        ):

            if cy0 > y:

                new_h = cy0 - y - 5

                if new_h > 30:

                    print(
                        f"  [CUT] Bottom caption removed at y={cy0}"
                    )

                    h = new_h

    crop = img[y:y + h, x:x + w].copy()

    if caption_top_y_px is not None:
        relative_cut_y = caption_top_y_px - y
        if 5 < relative_cut_y < crop.shape[0]:
            print(f"  [HARD CUT] Caption removed at y={caption_top_y_px}")
            crop = crop[:relative_cut_y, :]

    crop = remove_bottom_caption_text(crop)

    crop = trim_white_border(crop)

    if crop.shape[0] < 12 or crop.shape[1] < 12:
        return None

    # ============================================================
    # REJECT CAPTION-LIKE STRIPS
    # ============================================================

    gray_crop = cv2.cvtColor(
        crop,
        cv2.COLOR_BGR2GRAY
    )

    variance = np.var(gray_crop)

    aspect = crop.shape[1] / max(crop.shape[0], 1)

    if (
        aspect > 5
        and crop.shape[0] < page_h * 0.08
        and crop.shape[1] > page_w * 0.5
        and variance < 150
    ):
        print(
            "  [SKIP] Caption-like crop"
        )
        return None

    crop_rgb = cv2.cvtColor(
        crop,
        cv2.COLOR_BGR2RGB
    )

    return Image.fromarray(crop_rgb)

def normalize_fig_key(key):
    key = re.sub(r'[a-zA-Z]+$', '', key)
    key = re.sub(r'[-\.]+$', '', key)
    key = key.replace('-', '.')
    key = key.rstrip('.')
    parts = key.split('.')
    result_parts = []
    for p in parts:
        if p.isdigit():
            result_parts.append(str(int(p)))  # 02→2, 011→11, 10→10
        else:
            result_parts.append(p)
    return '.'.join(result_parts)


def parse_fig_key_from_text_data(text_data):

    cleaned = []
    for word, coords in text_data:
        w = re.sub(r'[\s\u00a0\u2002\u2003\u2009\u200b]+', '', word).strip()
        if w:
            cleaned.append((w, coords))
    text_data = cleaned

    # ------------------------------------------------------------------
    # Pattern 0: Standalone figure number 
    # ------------------------------------------------------------------

    has_f_pattern = False

    for word, _ in text_data:
        if re.search(r'\bf\d{2,3}-\d{2,3}',word,re.IGNORECASE):
            has_f_pattern = True
            break

    if not has_f_pattern:
        for word, _ in text_data:
            m = re.match(r'^(\d{1,3})\.(\d{1,3})([A-Za-z]*)$',word.strip())
            if m:

                chapter = m.group(1)
                figure  = m.group(2)
                suffix  = m.group(3).upper()

                key_norm = f"{chapter}.{figure}{suffix}"

                print(f"  [FIG-KEY] Pattern 0 standalone fig number: "f"'{key_norm}'")
                return key_norm, False
    # ------------------------------------------------------------------
    # Pattern 1: f01-02-03
    # ------------------------------------------------------------------
    for word, _ in text_data:
        m = re.search(r'\bf(\d{2,3}-\d{2,3}-\d{2,3})[a-z]*[-\.]', word, re.IGNORECASE)
        if m:
            return normalize_fig_key(m.group(1)), False
        
    # ------------------------------------------------------------------
    # Pattern 1B: (three-part with trailing letter)
    # ------------------------------------------------------------------

    for word, _ in text_data:
        m = re.search(r'\bf(\d{2,3}-\d{2,3}-\d{2,3}[a-z])[-\.]',word,re.IGNORECASE)
        if m:
            return normalize_fig_key(m.group(1)), False

    # ------------------------------------------------------------------
    # Pattern 2: f25-20a  (two-part with trailing letter)
    # ------------------------------------------------------------------
    for word, _ in text_data:
        m = re.search(r'\bf(\d{2,3}-\d{2,3})[a-z]+[-\.\d]', word, re.IGNORECASE)
        if m:
            return normalize_fig_key(m.group(1)), False

    # ------------------------------------------------------------------
    # Pattern 3: f24-02-9788131269008.eps  (two-part + ISBN)
    # ------------------------------------------------------------------
    for word, _ in text_data:
        m = re.search(r'\bf(\d{2,3}-\d{2,3})-\d{10,}', word, re.IGNORECASE)
        if m:
            return normalize_fig_key(m.group(1)), False

    # ------------------------------------------------------------------
    # Pattern 4: Fig: <token>
    # ------------------------------------------------------------------
    for i, (word, _) in enumerate(text_data):
        if word.lower() == 'fig:' and i + 1 < len(text_data):
            next_word = text_data[i + 1][0]
            next_word = re.sub(r'\.\w+$', '', next_word)
            next_word = re.sub(r'-\d{9,}$', '', next_word)
            if next_word:
                is_fx = not next_word.lower().startswith('f')
                if not is_fx:
                    # f-prefix: strip leading 'f' and normalize
                    key_body   = next_word[1:]              # strip 'f'
                    normalized = normalize_fig_key(key_body)
                    print(f"  [FIG-KEY] Pattern 4 f-prefix normalised: '{next_word}' -> '{normalized}'")
                    return normalized, False
                else:
                    print(f"  [FIG-KEY] Pattern 4 matched: '{next_word}' (FX candidate: True)")
                    return next_word, True

    # ------------------------------------------------------------------
    # Pattern 5: word-by-word
    # ------------------------------------------------------------------
    for word, _ in text_data:
        cleaned_word = word.strip().lower()
        m = re.search(r'\b([a-z]+)(\d{2,3})-([\w]+)', cleaned_word)
        if m:
            prefix      = m.group(1)
            rest        = m.group(0)
            key_raw     = re.sub(r'-\d{9,}.*$', '', rest)
            key_raw     = re.sub(r'\.\w+$', '', key_raw)

            if prefix == "f":
                chapter      = m.group(2)
                figure_part  = m.group(3)
                figure_clean = re.sub(r'[a-z].*$', '', figure_part)
                figure_clean = figure_clean.rstrip('-.')
                try:
                    key_normalized = f"{int(chapter)}.{int(figure_clean)}"
                except ValueError:
                    key_normalized = f"{chapter}.{figure_clean}"
                print(f"  [FIG-KEY] Pattern 5 f-prefix normalised: '{key_raw}' -> '{key_normalized}'")
                return key_normalized, False
            else:
                print(f"  [FIG-KEY] Pattern 5 non-f prefix FX candidate: '{key_raw}'")
                return key_raw, True

    # ------------------------------------------------------------------
    # Pattern 5 fallback: join all words
    # ------------------------------------------------------------------
    full_text = "".join(w for w, _ in text_data).lower()
    m = re.search(r'([a-z]+)(\d{2,3})-([\w-]+)', full_text)
    if m:
        prefix      = m.group(1)
        rest        = m.group(0)
        key_raw     = re.sub(r'-\d{9,}.*$', '', rest)
        key_raw     = re.sub(r'\.\w+$', '', key_raw)

        if prefix == "f":
            chapter      = m.group(2)
            figure_part  = m.group(3)
            figure_clean = re.sub(r'[a-z].*$', '', figure_part)
            figure_clean = figure_clean.rstrip('-.')
            try:
                key_normalized = f"{int(chapter)}.{int(figure_clean)}"
            except ValueError:
                key_normalized = f"{chapter}.{figure_clean}"
            print(f"  [FIG-KEY] Pattern 5 (joined) f-prefix normalised: '{key_raw}' -> '{key_normalized}'")
            return key_normalized, False
        else:
            print(f"  [FIG-KEY] Pattern 5 (joined) non-f prefix FX candidate: '{key_raw}'")
            return key_raw, True

    return None, False


# ─────────────────────────────────────────────────────────────────────────────
# Extract full image filename from page text (e.g. f01-01-9780443379321)
# ─────────────────────────────────────────────────────────────────────────────
def parse_image_filename_from_text_data(text_data):
    """
    Looks for the full image filename pattern in the page text.
    Patterns:
      - f01-01-9780443379321
      - f02-01-9780443380143.eps
      - Fig: f56-01-9780443287657.eps
    Returns the filename without extension (e.g. 'f01-01-9780443379321') or None.
    """
    cleaned = []
    for word, coords in text_data:
        w = re.sub(r'[\s\u00a0\u2002\u2003\u2009\u200b]+', '', word).strip()
        if w:
            cleaned.append((w, coords))
    text_data = cleaned

    # Pattern: fXX-XX-ISBN (with optional .ext suffix)
    # The ISBN is typically 13 digits (978...)
    for word, _ in text_data:
        m = re.search(r'(f\d{1,3}-\d{1,3}-\d{10,13})', word, re.IGNORECASE)
        if m:
            filename = m.group(1)
            # Remove any trailing extension like .eps, .jpg, .png
            filename = re.sub(r'\.\w+$', '', filename)
            print(f"  [IMG-NAME] Found: '{filename}'")
            return filename

    # Check after "Fig:" token
    for i, (word, _) in enumerate(text_data):
        if word.lower() in ('fig:', 'fig') and i + 1 < len(text_data):
            next_word = text_data[i + 1][0]
            m = re.search(r'(f\d{1,3}-\d{1,3}-\d{10,13})', next_word, re.IGNORECASE)
            if m:
                filename = m.group(1)
                filename = re.sub(r'\.\w+$', '', filename)
                print(f"  [IMG-NAME] Found after Fig: '{filename}'")
                return filename

    # Fallback: join all words and search
    full_text = "".join(w for w, _ in text_data)
    m = re.search(r'(f\d{1,3}-\d{1,3}-\d{10,13})', full_text, re.IGNORECASE)
    if m:
        filename = m.group(1)
        filename = re.sub(r'\.\w+$', '', filename)
        print(f"  [IMG-NAME] Found (joined): '{filename}'")
        return filename

    print(f"  [IMG-NAME] No image filename found")
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Group and stitch sub-figures
# ─────────────────────────────────────────────────────────────────────────────
def group_images_by_fig_number(images_with_keys):
    groups = OrderedDict()
    filenames = OrderedDict()
    for key, img, filename in images_with_keys:
        groups.setdefault(key, []).append(img)
        if key not in filenames and filename:
            filenames[key] = filename

    stitched = OrderedDict()
    for key, imgs in groups.items():
        if len(imgs) == 1:
            stitched[key] = (imgs[0], filenames.get(key))
        else:
            target_h = max(im.height for im in imgs)
            resized = []
            for im in imgs:
                if im.height != target_h:
                    ratio = target_h / im.height
                    im = im.resize((int(im.width * ratio), target_h), Image.LANCZOS)
                resized.append(im)

            gap = 6
            total_w = sum(im.width for im in resized) + gap * (len(resized) - 1)
            composite = Image.new("RGB", (total_w, target_h), (255, 255, 255))
            x_offset = 0
            for im in resized:
                composite.paste(im, (x_offset, 0))
                x_offset += im.width + gap
            stitched[key] = (composite, filenames.get(key))

    return stitched


# ─────────────────────────────────────────────────────────────────────────────
# MAIN EXTRACTION FUNCTION
# ─────────────────────────────────────────────────────────────────────────────
def extract_images_from_pdf(pdf_path):

    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        print(f"[ERROR] Failed to open PDF: {e}")
        return []

    page_images = render_pdf_pages_to_images(doc, scale=RENDER_SCALE)
    extracted_images = []

    fx_key_map: dict[str, str] = {}   # raw_key  →  FXn label
    fx_counter = 0

    for page_num, (img, scale) in page_images.items():
        page_height_pdf_pts = doc[page_num - 1].rect.height

        # Extract text
        text_data = extract_text_from_page(doc, page_num)
        has_caption, caption_bbox = is_caption_text_pattern(
            text_data, page_height_pdf_pts, scale_factor=scale
        )

        # Detect content regions
        page_h, page_w = img.shape[:2]

        # Use keyword-based Y for precise caption removal before detection
        caption_cut_y = find_caption_top_y_by_keywords(
            text_data, page_height_pdf_pts, scale_factor=scale
        )
        if caption_cut_y is None:
            caption_cut_y = int(page_h * 0.72)

        img = img.copy()
        img[caption_cut_y:, :] = 255   # white out caption before box detection

        # Pass caption_cut_y so the morphological close kernel cannot bridge
        # waveform content with caption pixels.
        boxes = detect_content_regions(img, caption_cut_y=caption_cut_y)

        # Find captions near images
        near_caption_bbox = find_near_image_captions(
            text_data, boxes, page_height_pdf_pts,
            scale_factor=scale, proximity_px=140
        )

        if near_caption_bbox:
            if caption_bbox:
                cx0 = min(caption_bbox[0], near_caption_bbox[0])
                cy0 = max(caption_bbox[1], near_caption_bbox[1])
                cx1 = max(caption_bbox[2], near_caption_bbox[2])
                cy1 = max(caption_bbox[3], near_caption_bbox[3])
                caption_bbox = (cx0, cy0, cx1, cy1)
            else:
                caption_bbox = near_caption_bbox
       
        # ── STEP 0.5: Parse full image filename ───────────────────────────
        image_filename = parse_image_filename_from_text_data(text_data)

        # ── STEP 1: Parse fig key ─────────────────────────────────────────

        raw_key, is_fx_candidate = parse_fig_key_from_text_data(text_data)

        # ------------------------------------------------------------
        # CASE 1 — No key found → assign FX label
        # ------------------------------------------------------------

        if raw_key is None:

            fx_counter += 1
            fig_key = f"FX{fx_counter}"

            print(f"  [FIG-KEY] No key found Page {page_num} — "f"assigned '{fig_key}'" )

        # ------------------------------------------------------------
        # CASE 2 — Non-f prefix → FX mapping
        # ------------------------------------------------------------

        elif is_fx_candidate:

            if raw_key not in fx_key_map:

                fx_counter += 1

                fx_key_map[raw_key] = f"FX{fx_counter}"

                print(f"  [FIG-KEY] Non-f prefix '{raw_key}' → "f"assigned label '{fx_key_map[raw_key]}'")

            else:

                print(f"  [FIG-KEY] Non-f prefix '{raw_key}' → "f"reusing label '{fx_key_map[raw_key]}'")

            fig_key = fx_key_map[raw_key]

        # ------------------------------------------------------------
        # CASE 3 — Standard figure → FORCE NORMALIZATION
        # ------------------------------------------------------------

        else:

            key = raw_key.strip()

            if key.lower().startswith("f"):
                key = key[1:]
            key = normalize_fig_key(key)

            fig_key = key

            print(
                f"  [FIG-KEY] Final normalized key: "
                f"'{raw_key}' → '{fig_key}'"
            ) 
        
        # ── STEP 2: Extract image ─────────────────────────────────────────
        extracted_img = extract_image_from_page(
            img, boxes, caption_bbox,
            text_data=text_data,
            page_height_pdf_pts=page_height_pdf_pts,
            scale_factor=scale
        )

        if extracted_img:
            width, height = extracted_img.size
            page_h, page_w = img.shape[:2]

            # Skip only if clearly a bottom caption strip
            if caption_bbox:
                cx0, cy0, cx1, cy1 = caption_bbox
                if (
                    width > page_w * 0.60
                    and height < page_h * 0.12
                    and cy0 > page_h * 0.75
                ):
                    print(f"  ✗ Page {page_num} skipped (bottom caption: {width}x{height})")
                    continue

            extracted_images.append((fig_key, extracted_img, image_filename))
            print(f"  ✓ Page {page_num} extracted | key='{fig_key}' | filename='{image_filename}'")
        else:
            print(f"  ✗ Page {page_num} skipped (no content)")

    doc.close()

    key_counts = Counter(k for k, _, _ in extracted_images)
    print(f"\n  [GROUP] Total pages extracted: {len(extracted_images)}")
    for key, count in key_counts.items():
        if count > 1:
            print(f"  [GROUP] '{key}' → {count} pages → STITCHING into 1 image")
        else:
            print(f"  [GROUP] '{key}' → 1 page → single image")

    grouped = group_images_by_fig_number(extracted_images)
    print(f"  [GROUP] Final: {len(grouped)} unique figures\n")

    # Return list of (fig_key, image, image_filename)
    return [(key, img, fname) for key, (img, fname) in grouped.items()]
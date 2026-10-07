
import json
import os
import boto3
import urllib.parse
import base64
import os
import requests
from gemini_AI_Model import GeminiImageProcessor

processor = GeminiImageProcessor()

s3 = boto3.client("s3")

TMP_DIR = "/tmp"
IMAGE_PREFIX = "gemini-In/"
TEXT_PREFIX = "gemini-txt/"
OUTPUT_PREFIX = "gemini-Out/"

def lambda_handler(event, context):
    print("✅ Lambda triggered successfully")

    record = event["Records"][0]
    bucket_name = record["s3"]["bucket"]["name"]
    object_key = urllib.parse.unquote_plus(
        record["s3"]["object"]["key"]
    )

    print(f"🪣 Bucket: {bucket_name}")
    print(f"📄 Object key: {object_key}")

    file_name = os.path.basename(object_key)
    base_name, ext = os.path.splitext(file_name)

    # ------------------------------------------------
    # Detect source & build matching file paths
    # ------------------------------------------------
    if object_key.startswith(IMAGE_PREFIX):
        image_key = object_key
        text_key = f"{TEXT_PREFIX}{base_name}.txt"
        print("🖼️ Image trigger detected")

    elif object_key.startswith(TEXT_PREFIX):
        text_key = object_key
        image_key = f"{IMAGE_PREFIX}{base_name}.jpg"  # change ext if needed
        print("📄 Text trigger detected")

    else:
        print("⚠️ File not from expected folders. Skipping.")
        return {"statusCode": 200, "body": "Ignored file"}

    local_image_path = os.path.join(TMP_DIR, os.path.basename(image_key))
    local_text_path = os.path.join(TMP_DIR, os.path.basename(text_key))

    # ------------------------------------------------
    # Download image & text
    # ------------------------------------------------
    s3.download_file(bucket_name, image_key, local_image_path)
    print(f"⬇️ Image downloaded: {local_image_path}")

    s3.download_file(bucket_name, text_key, local_text_path)
    print(f"⬇️ Text downloaded: {local_text_path}")

    # ------------------------------------------------
    # Read caption text
    # ------------------------------------------------
    with open(local_text_path, "r") as f:
        caption = f.read()

    # ------------------------------------------------
    # 🚀 Process image + caption
    # ------------------------------------------------
    print("🚀 Calling Gemini processor...")
    result_dict = processor.process_image(local_image_path, caption)

    if not isinstance(result_dict, dict):
        raise ValueError("Processing function must return a dict")

    print("✅ Processing successful")

    # ------------------------------------------------
    # 💾 Save JSON
    # ------------------------------------------------
    json_file_name = f"{base_name}.json"
    local_json_path = os.path.join(TMP_DIR, json_file_name)

    with open(local_json_path, "w") as f:
        json.dump(result_dict, f, indent=2)

    # ------------------------------------------------
    # ☁️ Upload JSON to S3
    # ------------------------------------------------
    output_key = f"{OUTPUT_PREFIX}{json_file_name}"
    s3.upload_file(local_json_path, bucket_name, output_key)

    print(f"📤 JSON uploaded: s3://{bucket_name}/{output_key}")

    return {
        "statusCode": 200,
        "body": "Processing completed successfully"
    }

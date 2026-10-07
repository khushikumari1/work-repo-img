"""
watch_dog.py
─────────────
Monitors WATCH_DIRECTORY for new folders arriving on the network share.
When a new folder appears it is copied to OUT_BASE_DIRECTORY, then the
full IDTF pipeline is run on every chapter sub-folder inside it.

All path and timing settings live in config.py — nothing is hardcoded here.

Usage
-----
    python watch_dog.py
"""

import time
import os
import shutil
import logging

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from config import WATCH_DIRECTORY, OUT_BASE_DIRECTORY, WAIT_SECONDS
from frontlist_script import generate_IDTF_first_step

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


class FolderCreationHandler(FileSystemEventHandler):
    """Fires when a new top-level folder appears inside WATCH_DIRECTORY."""

    def on_created(self, event):
        if not event.is_directory:
            return

        source_path = event.src_path
        folder_name = os.path.basename(source_path)
        destination_path = os.path.join(OUT_BASE_DIRECTORY, folder_name)

        logger.info(f"New folder detected: {source_path}")
        logger.info(
            f"Waiting {WAIT_SECONDS}s for file transfer to finish before copying..."
        )
        time.sleep(WAIT_SECONDS)

        logger.info(f"Copying folder to output: {destination_path}")
        shutil.copytree(source_path, destination_path)

        # Walk every sub-folder inside the copied folder and process each one
        for root, dirs, files in os.walk(destination_path):
            for dir_name in dirs:
                chapter_folder_path = os.path.join(root, dir_name)
                logger.info(f"Processing chapter folder: {chapter_folder_path}")
                generate_IDTF_first_step(chapter_folder_path)

        logger.info(f"All chapters processed in: {destination_path}")


def monitor_folder():
    """Start the watchdog observer and block until KeyboardInterrupt."""
    event_handler = FolderCreationHandler()
    observer = Observer()
    observer.schedule(event_handler, WATCH_DIRECTORY, recursive=False)
    observer.start()
    logger.info(f"Watching: {WATCH_DIRECTORY}")
    logger.info(f"Output:   {OUT_BASE_DIRECTORY}")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Stopping watchdog...")
        observer.stop()

    observer.join()
    logger.info("Watchdog stopped.")


if __name__ == "__main__":
    monitor_folder()

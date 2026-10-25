"""Download and unzip the FAERS/AEMS quarterly ASCII files from the FDA.

Usage (from the repository root, with the 'faers' conda env active):

    python src/faers/ingest.py --start 2025q3 --end 2026q2   # small test
    python src/faers/ingest.py                               # full window
"""

import argparse
import sys
import time
import zipfile
from pathlib import Path

import requests

URL_TEMPLATE = "https://fis.fda.gov/content/Exports/faers_ascii_{year}{quarter}.zip"
DEFAULT_START = "2014q3"
DEFAULT_END = "2026q2"
RAW_DIR = Path("data/raw")


def parse_quarter(text):
    """Convert '2014q3' into (2014, 3)."""
    year, quarter = text.lower().split("q")
    return int(year), int(quarter)


def quarter_range(start, end):
    """List every (year, quarter) from start to end, both included."""
    year, quarter = parse_quarter(start)
    last = parse_quarter(end)
    quarters = []
    while (year, quarter) <= last:
        quarters.append((year, quarter))
        quarter += 1
        if quarter == 5:
            year, quarter = year + 1, 1
    return quarters


def candidate_urls(year, quarter):
    """The FDA is not consistent: some files end in 'q3', others in 'Q3'."""
    return [
        URL_TEMPLATE.format(year=year, quarter=f"q{quarter}"),
        URL_TEMPLATE.format(year=year, quarter=f"Q{quarter}"),
    ]


def already_downloaded(folder):
    """True if the folder exists and already contains .txt files."""
    if not folder.exists():
        return False
    return any(path.suffix.lower() == ".txt" for path in folder.rglob("*"))


def download(url, destination):
    """Download url into destination. Return False if the file does not exist."""
    response = requests.get(url, stream=True, timeout=60)
    if response.status_code == 404:
        return False
    response.raise_for_status()
    partial = destination.with_suffix(".part")
    with open(partial, "wb") as file:
        file.writelines(response.iter_content(chunk_size=1024 * 1024))
    partial.rename(destination)
    return True


def fetch_quarter(year, quarter, raw_dir):
    """Download and unzip one quarter. Return True if it is available."""
    name = f"faers_ascii_{year}q{quarter}"
    folder = raw_dir / name
    if already_downloaded(folder):
        print(f"{name}: already there, skipping")
        return True

    zip_path = raw_dir / f"{name}.zip"
    for url in candidate_urls(year, quarter):
        if download(url, zip_path):
            break
    else:
        print(f"{name}: NOT FOUND on the FDA server")
        return False

    # Unzip into a temporary folder first, so an interrupted run
    # never leaves a half-extracted quarter that looks complete.
    temporary = raw_dir / f"{name}.tmp"
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(temporary)
    temporary.rename(folder)
    zip_path.unlink()
    print(f"{name}: downloaded and unzipped")
    return True


def main():
    parser = argparse.ArgumentParser(description="Download FAERS quarterly files.")
    parser.add_argument("--start", default=DEFAULT_START, help="e.g. 2014q3")
    parser.add_argument("--end", default=DEFAULT_END, help="e.g. 2026q2")
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    args = parser.parse_args()

    args.raw_dir.mkdir(parents=True, exist_ok=True)
    quarters = quarter_range(args.start, args.end)
    failed = []
    for year, quarter in quarters:
        if not fetch_quarter(year, quarter, args.raw_dir):
            failed.append(f"{year}q{quarter}")
        time.sleep(1)  # be polite with the FDA server

    n_ok = len(quarters) - len(failed)
    print(f"\nDone: {n_ok} of {len(quarters)} quarters available.")
    if failed:
        print("Missing:", ", ".join(failed))
        sys.exit(1)


if __name__ == "__main__":
    main()
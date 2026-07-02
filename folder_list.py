#!/usr/bin/env python3
"""
Advanced Video Folder Indexer (Final Version)

Features:
 - Creates versioned result folder: result-list--vX
 - Generates TXT, HTML, and JSON outputs
 - Logs operations and copies results to project folder
 - Duration displayed in minutes or hours+minutes
 - Table sorted by video duration
 - DIR column added with clickable folder links
 - Title column links to video file (opens in new tab)
"""

import os
import sys
import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# ---------- Configuration ----------
VIDEO_EXTS = {'.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.mpeg', '.mpg', '.m4v'}
SUB_EXTS = {'.srt', '.txt'}
MAX_WORKERS = 8
FFPROBE_PATH = r"C:\Users\Developer\ffmpeg\bin\ffprobe.exe"
# -----------------------------------

def log(msg: str, log_file=None):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{timestamp}] {msg}"
    print(line)
    if log_file:
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(line + '\n')

def human_dt(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')

def get_duration_seconds_ffprobe(path: str) -> float | None:
    try:
        res = subprocess.run(
            [FFPROBE_PATH, '-v', 'error', '-select_streams', 'v:0',
             '-show_entries', 'format=duration',
             '-of', 'default=noprint_wrappers=1:nokey=1', path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        out = res.stdout.strip()
        if not out:
            return None
        return float(out)
    except Exception:
        return None

def has_subtitle(video_path: Path) -> bool:
    folder = video_path.parent
    base = video_path.stem
    for ext in SUB_EXTS:
        if (folder / (base + ext)).exists():
            return True
    for f in folder.iterdir():
        if f.is_file() and f.suffix.lower() in SUB_EXTS and base.lower() in f.stem.lower():
            return True
    return False

def duration_to_human(minutes: float | None) -> str:
    if minutes is None:
        return "unknown"
    mins = int(round(minutes))
    if mins < 60:
        return f"{mins} min"
    h, m = divmod(mins, 60)
    return f"{h}h {m}min"

def make_safe_name_from_path(path: Path) -> str:
    s = str(path).replace(':', '').replace('\\', '/').strip('/')
    parts = [p for p in s.split('/') if p]
    safe_name = '_'.join(parts)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M')
    return f"{safe_name}--{timestamp}--"

def next_version_folder(base_folder: Path) -> Path:
    base_name_prefix = "result-list--"
    existing = [p for p in base_folder.iterdir() if p.is_dir() and p.name.startswith(base_name_prefix)]
    v = 1
    if existing:
        while any(p.name.endswith(f"v{v}") for p in existing):
            v += 1
    folder_name = f"{base_name_prefix}v{v}"
    folder = base_folder / folder_name
    folder.mkdir(parents=True, exist_ok=True)
    return folder

def analyze_video(base_folder: Path, path: Path, log_file) -> dict:
    stat = path.stat()
    size_mb = round(stat.st_size / (1024 * 1024), 2)
    dur_sec = get_duration_seconds_ffprobe(str(path))
    dur_min = round(dur_sec / 60, 2) if dur_sec else None
    rel_dir = str(path.parent.relative_to(base_folder))

    info = {
        "title": path.stem.replace('_', ' '),
        "abs_path": str(path.resolve()),
        "rel_path": str(path.relative_to(base_folder)),
        "dir": rel_dir,
        "size_mb": size_mb,
        "ctime": human_dt(stat.st_ctime),
        "duration_minutes": int(dur_min) if dur_min else None,
        "duration_human": duration_to_human(dur_min),
    }
    log(f"Indexed: {info['rel_path']}", log_file)
    return info

def gather_videos(base_folder: Path):
    files = []
    for root, _, filenames in os.walk(base_folder):
        for name in filenames:
            if Path(name).suffix.lower() in VIDEO_EXTS:
                files.append(Path(root) / name)
    return files

def write_txt(index_list: list[dict], out_path: Path, base_name: str, log_file):
    out_file = out_path / f"{base_name}.txt"
    with out_file.open("w", encoding="utf-8") as f:
        f.write(f"Video Index Report\nGenerated: {datetime.now()}\n")
        f.write(f"Total files: {len(index_list)}\n\n")
        for i, it in enumerate(index_list, 1):
            f.write(f"[{i}] {it['title']}\n")
            f.write(f"DIR: {it['dir']}\n")
            f.write(f"Size: {it['size_mb']} MB\n")
            f.write(f"Created: {it['ctime']}\n")
            f.write(f"Duration: {it['duration_human']}\n\n")
    log(f"TXT file created: {out_file}", log_file)

def write_json(index_list: list[dict], out_path: Path, base_name: str, log_file):
    out_file = out_path / f"{base_name}.json"
    with out_file.open("w", encoding="utf-8") as f:
        json.dump(index_list, f, indent=2, ensure_ascii=False)
    log(f"JSON file created: {out_file}", log_file)

def write_html(index_list: list[dict], out_path: Path, base_name: str, log_file, base_folder: Path):
    out_file = out_path / f"{base_name}.html"
    total_files = len(index_list)
    total_duration = sum(i["duration_minutes"] or 0 for i in index_list)
    total_size = sum(i["size_mb"] for i in index_list)
    total_size_text = f"{round(total_size / 1024, 2)} GB" if total_size >= 1024 else f"{int(total_size)} MB"
    total_hours = int(total_duration // 60)
    total_minutes = int(total_duration % 60)

    index_list.sort(key=lambda x: x["duration_minutes"] or 0, reverse=True)

    style = """
    body{font-family:Segoe UI,Roboto,Arial;margin:20px;background:#f9fafb;color:#222}
    table{border-collapse:collapse;width:100%;margin-top:1em}
    th,td{padding:8px 10px;border-bottom:1px solid #ddd;text-align:left}
    tr:nth-child(even){background:#f2f2f2}
    th{background:#e5e7eb}
    a{color:#0078d7;text-decoration:none}a:hover{text-decoration:underline}
    """

    with out_file.open("w", encoding="utf-8") as f:
        f.write("<!doctype html><html><head><meta charset='utf-8'>")
        f.write("<title>Video Index</title>")
        f.write(f"<style>{style}</style></head><body>")
        f.write("<h1>Video Index Report</h1>")
        f.write(f"<p><b>Folder:</b> <a href='file://{base_folder.resolve()}' target='_blank'>{base_folder.resolve()}</a></p>")
        f.write(f"<p><b>Total files:</b> {total_files} | <b>Total size:</b> {total_size_text} | "
                f"<b>Total duration:</b> {int(total_duration)} min (≈ {total_hours}h {total_minutes}min)</p>")

        f.write("<table><tr><th>#</th><th>DIR</th><th>Title</th><th>Duration</th><th>Size</th><th>Created</th></tr>")
        for i, it in enumerate(index_list, 1):
            # لینک برای تمام فولدرهای مسیر
            dir_parts = it["dir"].split(os.sep)
            dir_links = []
            path_acc = Path(base_folder)
            for part in dir_parts:
                path_acc = path_acc / part
                href_dir = "file://" + str(path_acc.resolve())
                dir_links.append(f"<a href='{href_dir}' target='_blank'>{part}</a>")
            dir_html = " / ".join(dir_links)
            href_file = "file://" + it["abs_path"].replace(" ", "%20")
            dur = it["duration_human"]
            size = int(it["size_mb"])
            f.write(f"<tr><td>{i}</td>"
                    f"<td>{dir_html}</td>"
                    f"<td><a href='{href_file}' target='_blank'>{it['title']}</a></td>"
                    f"<td>{dur}</td>"
                    f"<td>{size}</td>"
                    f"<td>{it['ctime']}</td></tr>")
        f.write("</table></body></html>")
    log(f"HTML file created: {out_file}", log_file)

def copy_results_to_project(out_folder: Path, base_folder: Path, log_file):
    project_root = Path.cwd()
    safe_name = make_safe_name_from_path(base_folder)
    dest = project_root / safe_name
    dest.mkdir(parents=True, exist_ok=True)
    for file in out_folder.iterdir():
        if file.is_file():
            shutil.copy2(file, dest / file.name)
    log(f"Backup copied to: {dest}", log_file)

def index_folder(base_folder: Path):
    out_folder = next_version_folder(base_folder)
    log_file = out_folder / "index.log"
    log(f"Indexing started in {base_folder}", log_file)

    videos = gather_videos(base_folder)
    log(f"Found {len(videos)} video(s)", log_file)

    base_name = make_safe_name_from_path(base_folder).rstrip('-')

    index_data = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(analyze_video, base_folder, v, log_file): v for v in videos}
        for fut in as_completed(futures):
            try:
                index_data.append(fut.result())
            except Exception as e:
                log(f"Error processing {futures[fut]}: {e}", log_file)

    write_txt(index_data, out_folder, base_name, log_file)
    write_html(index_data, out_folder, base_name, log_file, base_folder)
    write_json(index_data, out_folder, base_name, log_file)
    copy_results_to_project(out_folder, base_folder, log_file)

    log("Indexing complete.", log_file)

def main():
    print("=== Video Folder Indexer (Final Version) ===")
    base_input = input("Enter the folder path to scan: ").strip()
    base_folder = Path(base_input)
    if not base_folder.exists() or not base_folder.is_dir():
        print(f"Error: '{base_folder}' is not a valid folder.")
        sys.exit(1)
    index_folder(base_folder)

if __name__ == "__main__":
    main()

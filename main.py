import asyncio
import json
import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Optional

import aiofiles
import psutil
from fastapi import FastAPI, HTTPException, Query, UploadFile, File
from fastapi.responses import FileResponse, StreamingResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

app = FastAPI(title="MediaForge")

jobs: dict = {}


def _public_job(job: dict) -> dict:
    return {k: v for k, v in job.items() if not k.startswith("_")}

STATIC_DIR = Path(__file__).parent / "static"
UPLOAD_DIR = Path(__file__).parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

OUTPUTS_DIR = Path(__file__).parent / "outputs"
OUTPUTS_DIR.mkdir(exist_ok=True)

DOWNLOADS_DIR = Path(__file__).parent / "downloads"
DOWNLOADS_DIR.mkdir(exist_ok=True)

OUTPUTS_LOG = Path(__file__).parent / "completed_outputs.json"


def _load_completed_outputs() -> list:
    if OUTPUTS_LOG.exists():
        try:
            return json.loads(OUTPUTS_LOG.read_text("utf-8"))
        except Exception:
            return []
    return []


def _persist_completed_output(job: dict):
    entry = {
        "tool": job.get("tool", "ffmpeg"),
        "output_path": job["output_path"],
        "job_id": job["id"],
        "type": job.get("type", ""),
        "input_path": job.get("input_path", ""),
        "params": job.get("params", {}),
        "command": job.get("command", ""),
    }
    completed_outputs.append(entry)
    try:
        OUTPUTS_LOG.write_text(json.dumps(completed_outputs, ensure_ascii=False), "utf-8")
    except Exception:
        pass


completed_outputs: list = _load_completed_outputs()

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# ── Capability detection (run once at startup) ────────────────────────────────

def _detect_capabilities() -> dict:
    caps = {}
    caps["ffmpeg"] = shutil.which("ffmpeg") is not None
    caps["ffprobe"] = shutil.which("ffprobe") is not None
    # imagemagick: modern = 'magick', legacy = 'convert'
    magick = shutil.which("magick")
    convert = shutil.which("convert")
    caps["imagemagick"] = magick is not None or convert is not None
    caps["imagemagick_cmd"] = "magick" if magick else ("convert" if convert else None)
    caps["yt_dlp"] = shutil.which("yt-dlp") is not None

    os_info = {}
    try:
        with open("/etc/os-release") as f:
            for line in f:
                line = line.strip()
                if "=" in line:
                    k, v = line.split("=", 1)
                    os_info[k] = v.strip('"')
    except Exception:
        pass
    caps["os_id"] = os_info.get("ID", "")
    caps["os_name"] = os_info.get("PRETTY_NAME", "")

    return caps


CAPABILITIES = _detect_capabilities()
CAPABILITIES["outputs_dir"] = str(OUTPUTS_DIR)
CAPABILITIES["downloads_dir"] = str(DOWNLOADS_DIR)
CAPABILITIES["uploads_dir"] = str(UPLOAD_DIR)


@app.get("/api/capabilities")
async def get_capabilities():
    return CAPABILITIES


@app.get("/")
async def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


# ── File system browser ───────────────────────────────────────────────────────

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff", ".tif",
              ".heic", ".heif", ".avif", ".svg", ".ico"}

VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".m4v", ".ts",
              ".mts", ".wmv", ".mpg", ".mpeg", ".m2v", ".3gp", ".ogv"}
PLAYABLE_EXTS = {".mp4", ".webm", ".ogg", ".ogv", ".mov"}


@app.get("/api/browse")
async def browse(path: str = Query(default=str(Path.home()))):
    p = Path(path).expanduser().resolve()
    if not p.exists():
        raise HTTPException(404, f"Path not found: {p}")

    if p.is_file():
        return {"path": str(p), "parent": str(p.parent), "entries": [], "is_file": True}

    entries = []
    try:
        for entry in sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            try:
                stat = entry.stat()
                entries.append({
                    "name": entry.name,
                    "path": str(entry),
                    "is_dir": entry.is_dir(),
                    "size": stat.st_size if entry.is_file() else None,
                    "is_video": entry.suffix.lower() in VIDEO_EXTS,
                    "is_image": entry.suffix.lower() in IMAGE_EXTS,
                })
            except (PermissionError, OSError):
                pass
    except PermissionError:
        pass

    return {
        "path": str(p),
        "parent": str(p.parent) if str(p) != str(p.parent) else None,
        "entries": entries,
        "is_file": False,
    }


# ── Upload / Download ─────────────────────────────────────────────────────────

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    safe_name = Path(file.filename).name if file.filename else "upload"
    dest = UPLOAD_DIR / safe_name
    if dest.exists():
        stem = dest.stem
        suffix = dest.suffix
        dest = UPLOAD_DIR / f"{stem}_{str(uuid.uuid4())[:6]}{suffix}"

    async with aiofiles.open(dest, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            await f.write(chunk)

    stat = dest.stat()
    return {
        "path": str(dest),
        "name": dest.name,
        "size": stat.st_size,
        "is_video": dest.suffix.lower() in VIDEO_EXTS,
        "is_image": dest.suffix.lower() in IMAGE_EXTS,
    }


@app.get("/api/download")
async def download_file(path: str):
    fp = Path(path)
    if not fp.exists() or not fp.is_file():
        raise HTTPException(404, "File not found")
    return FileResponse(
        str(fp),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{fp.name}"'},
    )


@app.get("/api/uploads")
async def list_uploads():
    entries = []
    for f in sorted(UPLOAD_DIR.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        if f.is_file():
            stat = f.stat()
            entries.append({
                "name": f.name,
                "path": str(f),
                "size": stat.st_size,
                "is_video": f.suffix.lower() in VIDEO_EXTS,
                "is_image": f.suffix.lower() in IMAGE_EXTS,
            })
    return entries


@app.get("/api/output-files")
async def list_output_files():
    """Return files produced by completed jobs (ffmpeg, imagemagick, yt-dlp).

    Combines current session's in-memory done jobs with the persisted log so
    files from previous server sessions are also visible on startup.
    """
    MEDIA_EXTS = VIDEO_EXTS | IMAGE_EXTS | {
        ".mp3", ".m4a", ".aac", ".flac", ".opus", ".ogg", ".wav",
        ".mkv", ".webm",
    }
    seen: set[str] = set()
    entries = []

    # Build a deduplicated source list: current-session done jobs first (most
    # recent), then the persisted log (which covers previous sessions).
    current_done = [j for j in reversed(list(jobs.values())) if j["status"] == "done"]
    current_ids = {j["id"] for j in current_done}
    past = [o for o in reversed(completed_outputs) if o["job_id"] not in current_ids]
    sources = current_done + past

    def _add_file(f: Path, tool: str, job_id: str):
        key = str(f)
        if key in seen:
            return
        if not f.is_file():
            return
        seen.add(key)
        stat = f.stat()
        entries.append({
            "name": f.name,
            "path": str(f),
            "size": stat.st_size,
            "is_video": f.suffix.lower() in VIDEO_EXTS,
            "is_image": f.suffix.lower() in IMAGE_EXTS,
            "source": tool,
            "job_id": job_id,
        })

    for src in sources:
        tool = src.get("tool", "ffmpeg")
        job_id = src["job_id"] if "job_id" in src else src.get("id", "")
        output_path = src["output_path"] if "output_path" in src else src.get("output_path", "")
        out = Path(output_path)

        if tool == "yt-dlp":
            if not out.is_dir():
                continue
            try:
                for f in sorted(out.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
                    if f.is_file() and f.suffix.lower() in MEDIA_EXTS:
                        _add_file(f, tool, job_id)
            except (PermissionError, OSError):
                pass
        else:
            _add_file(out, tool, job_id)

    return entries


@app.delete("/api/output-files")
async def delete_output_file(path: str):
    fp = Path(path).resolve()
    if not fp.exists() or not fp.is_file():
        raise HTTPException(404, "File not found")
    fp.unlink()
    return {"ok": True}


@app.delete("/api/uploads/{filename}")
async def delete_upload(filename: str):
    fp = UPLOAD_DIR / Path(filename).name
    if not fp.exists():
        raise HTTPException(404, "File not found")
    fp.unlink()
    return {"ok": True}


# ── Media serving ─────────────────────────────────────────────────────────────

@app.get("/api/media")
async def serve_media(path: str):
    fp = Path(path)
    if not fp.exists() or not fp.is_file():
        raise HTTPException(404, "File not found")
    return FileResponse(str(fp), media_type=_mime(fp))


@app.get("/api/thumbnail")
async def thumbnail(path: str, t: str = "00:00:02", w: int = 640):
    fp = Path(path)
    if not fp.exists():
        raise HTTPException(404, "File not found")

    # Image file: serve directly via imagemagick resize, or just return the file
    if fp.suffix.lower() in IMAGE_EXTS:
        if CAPABILITIES["imagemagick"] and CAPABILITIES["imagemagick_cmd"]:
            cmd_name = CAPABILITIES["imagemagick_cmd"]
            if cmd_name == "magick":
                cmd = ["magick", str(fp), "-thumbnail", f"{w}x", "-", ]
            else:
                cmd = ["convert", str(fp), "-thumbnail", f"{w}x", "-"]
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
            )
            stdout, _ = await proc.communicate()
            if proc.returncode == 0 and stdout:
                return Response(content=stdout, media_type="image/jpeg")
        return FileResponse(str(fp))

    cmd = [
        "ffmpeg", "-y", "-ss", t, "-i", str(fp),
        "-vframes", "1", "-vf", f"scale={w}:-1",
        "-f", "image2pipe", "-vcodec", "mjpeg", "pipe:1",
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
    )
    stdout, _ = await proc.communicate()
    if proc.returncode != 0 or not stdout:
        raise HTTPException(500, "Thumbnail generation failed")
    return Response(content=stdout, media_type="image/jpeg")


# ── ffprobe ───────────────────────────────────────────────────────────────────

@app.get("/api/probe")
async def probe(path: str):
    fp = Path(path)
    if not fp.exists():
        raise HTTPException(404, "File not found")
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", str(fp),
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise HTTPException(500, f"ffprobe error: {stderr.decode()[:200]}")
    return json.loads(stdout)


# ── File info (metadata + job provenance) ────────────────────────────────────

@app.get("/api/file-info")
async def file_info(path: str):
    fp = Path(path)
    if not fp.exists() or not fp.is_file():
        raise HTTPException(404, "File not found")

    stat = fp.stat()
    result: dict = {
        "name": fp.name,
        "path": str(fp),
        "size": stat.st_size,
        "mtime": stat.st_mtime,
        "suffix": fp.suffix.lower(),
        "is_video": fp.suffix.lower() in VIDEO_EXTS,
        "is_image": fp.suffix.lower() in IMAGE_EXTS,
        "media_info": None,
        "job": None,
    }

    # Media metadata via ffprobe (handles video, audio, and images)
    if CAPABILITIES.get("ffprobe"):
        try:
            cmd = [
                "ffprobe", "-v", "quiet", "-print_format", "json",
                "-show_format", "-show_streams", str(fp),
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
            )
            stdout, _ = await proc.communicate()
            if proc.returncode == 0:
                result["media_info"] = json.loads(stdout)
        except Exception:
            pass

    # Job provenance — check in-memory jobs first, then persisted log
    def _job_provenance(j: dict) -> dict:
        return {
            "id": j.get("job_id") or j.get("id", ""),
            "type": j.get("type", ""),
            "tool": j.get("tool", ""),
            "input_path": j.get("input_path", ""),
            "params": j.get("params", {}),
            "command": j.get("command", ""),
        }

    for job in jobs.values():
        if job.get("output_path") == str(fp) and job.get("status") == "done":
            result["job"] = _job_provenance(job)
            break

    if result["job"] is None:
        for entry in completed_outputs:
            if entry.get("output_path") == str(fp):
                result["job"] = _job_provenance(entry)
                break

    return result


# ── yt-dlp format list ────────────────────────────────────────────────────────

@app.get("/api/ytdlp/formats")
async def ytdlp_formats(url: str):
    if not CAPABILITIES["yt_dlp"]:
        raise HTTPException(503, "yt-dlp not available")

    # -J gives full JSON with all format info; --no-playlist processes only the
    # first item so we always get format details even for playlist URLs.
    run_env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    cmd = ["yt-dlp", "-J", "--no-playlist", url]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        env=run_env,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise HTTPException(400, f"yt-dlp error: {stderr.decode()[:300]}")

    data = json.loads(stdout)

    # yt-dlp sometimes wraps a single video in a playlist envelope even with
    # --no-playlist (e.g. YouTube short URLs).  Detect by the absence of
    # "formats" at the top level and fall through to entries[0].
    is_playlist = False
    if "formats" not in data and "entries" in data:
        raw_entries = data.get("entries") or []
        is_playlist = len(raw_entries) > 1
        data = raw_entries[0] if raw_entries else {}

    formats = [
        {
            "format_id": f.get("format_id"),
            "ext": f.get("ext"),
            "resolution": f.get("resolution") or f.get("format_note", ""),
            "height": f.get("height"),
            "fps": f.get("fps"),
            "vcodec": f.get("vcodec"),
            "acodec": f.get("acodec"),
            "filesize": f.get("filesize"),
            "tbr": f.get("tbr"),
        }
        for f in data.get("formats", [])
    ]

    # Pick best thumbnail (yt-dlp lists thumbnails ascending by quality)
    thumbnail = data.get("thumbnail", "")
    thumbnails = data.get("thumbnails") or []
    if thumbnails:
        thumbnail = thumbnails[-1].get("url", thumbnail)

    return {
        "title": data.get("title", ""),
        "thumbnail": thumbnail,
        "duration": data.get("duration"),
        "uploader": data.get("uploader") or data.get("channel", ""),
        "formats": formats,
        "is_playlist": is_playlist,
    }


# ── System stats ──────────────────────────────────────────────────────────────

@app.get("/api/system")
async def system_stats():
    cpu = psutil.cpu_percent(interval=0.1)
    mem = psutil.virtual_memory()
    temp_val = None
    try:
        temps = psutil.sensors_temperatures()
        if temps:
            for entries in temps.values():
                if entries:
                    temp_val = round(entries[0].current, 1)
                    break
    except Exception:
        pass

    active = sum(1 for j in jobs.values() if j["status"] == "running")
    return {
        "cpu_percent": cpu,
        "memory_percent": round(mem.percent, 1),
        "memory_used_gb": round(mem.used / 1e9, 1),
        "memory_total_gb": round(mem.total / 1e9, 1),
        "temperature": temp_val,
        "active_jobs": active,
    }


# ── Jobs ──────────────────────────────────────────────────────────────────────

class JobRequest(BaseModel):
    type: str
    input_path: str
    output_path: str
    params: dict = {}


@app.post("/api/jobs")
async def create_job(req: JobRequest):
    # yt-dlp jobs don't need an existing input file (input_path is a URL)
    if not req.type.startswith("ytdlp_") and not Path(req.input_path).exists():
        raise HTTPException(400, f"Input file not found: {req.input_path}")

    job_id = str(uuid.uuid4())[:8]
    cmd = _build_cmd(req.type, req.input_path, req.output_path, req.params)
    job = {
        "id": job_id,
        "type": req.type,
        "tool": _tool_for_type(req.type),
        "input_path": req.input_path,
        "output_path": req.output_path,
        "params": req.params,
        "status": "pending",
        "progress": 0,
        "speed": None,
        "fps": None,
        "log": [],
        "command": " ".join(str(c) for c in cmd),
        "duration_sec": None,
        "error": None,
    }
    jobs[job_id] = job
    asyncio.create_task(_run_job(job_id, cmd))
    return _public_job(job)


@app.get("/api/jobs")
async def list_jobs():
    return [_public_job(j) for j in reversed(list(jobs.values()))]


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, "Not found")
    return _public_job(jobs[job_id])


@app.delete("/api/jobs/{job_id}")
async def cancel_job(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, "Not found")
    job = jobs[job_id]
    proc = job.get("_proc")
    if proc and proc.returncode is None:
        proc.terminate()
    job["status"] = "cancelled"
    return {"ok": True}


@app.get("/api/jobs/{job_id}/stream")
async def stream_job(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, "Not found")

    async def generate():
        seen = 0
        while True:
            job = jobs.get(job_id)
            if not job:
                break
            log = job["log"]
            new_lines = log[seen:]
            if new_lines:
                seen = len(log)
                payload = json.dumps({
                    "log": new_lines,
                    "progress": job["progress"],
                    "speed": job["speed"],
                    "fps": job["fps"],
                    "status": job["status"],
                })
                yield f"data: {payload}\n\n"
            else:
                yield f"data: {json.dumps({'ping': True, 'progress': job['progress'], 'status': job['status']})}\n\n"

            if job["status"] in ("done", "error", "cancelled"):
                break
            await asyncio.sleep(0.3)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Command builders ──────────────────────────────────────────────────────────

def _tool_for_type(job_type: str) -> str:
    if job_type.startswith("image_"):
        return "imagemagick"
    if job_type.startswith("ytdlp_"):
        return "yt-dlp"
    return "ffmpeg"


def _build_cmd(job_type: str, inp: str, out: str, p: dict) -> list:
    if job_type.startswith("image_"):
        return _build_imagemagick_cmd(job_type, inp, out, p)
    if job_type.startswith("ytdlp_"):
        return _build_ytdlp_cmd(job_type, inp, out, p)
    return _build_ffmpeg_cmd(job_type, inp, out, p)


def _build_ffmpeg_cmd(job_type: str, inp: str, out: str, p: dict) -> list:
    # -progress pipe:1 sends structured key=value progress to stdout (newline-
    # terminated, works even when not a tty).  -nostats suppresses the redundant
    # stats line on stderr so the log stays clean.
    cmd = ["ffmpeg", "-y", "-progress", "pipe:1", "-nostats"]

    if job_type == "trim":
        start = p.get("start", "0")
        end = p.get("end", "")
        accurate = p.get("accurate", False)
        if not accurate:
            cmd += ["-ss", start, "-i", inp]
            if end:
                cmd += ["-to", end]
            cmd += ["-c", "copy"]
        else:
            cmd += ["-i", inp, "-ss", start]
            if end:
                cmd += ["-to", end]
            cmd += ["-c:v", "libx264", "-c:a", "copy"]
        cmd.append(out)

    elif job_type == "crop":
        cw = p.get("w", 1280)
        ch = p.get("h", 720)
        cx = p.get("x", 0)
        cy = p.get("y", 0)
        vf = f"crop={cw}:{ch}:{cx}:{cy}"
        scale = p.get("scale", "")
        if scale:
            vf += f",scale={scale}"
        vcodec = p.get("vcodec", "libopenh264")
        crf = p.get("crf", 23)
        cmd += ["-i", inp, "-vf", vf, "-c:v", vcodec, "-crf", str(crf), "-c:a", "copy", out]

    elif job_type == "convert":
        hw = p.get("hwaccel", "")
        if hw and hw != "none":
            cmd += ["-hwaccel", hw]
        cmd += ["-i", inp]

        vcodec = p.get("vcodec", "libopenh264")
        acodec = p.get("acodec", "aac")

        if vcodec == "copy":
            cmd += ["-c:v", "copy"]
        else:
            cmd += ["-c:v", vcodec]
            crf = p.get("crf")
            bitrate = p.get("bitrate")
            if crf is not None:
                cmd += ["-crf", str(crf)]
            elif bitrate:
                cmd += ["-b:v", bitrate]
            res = p.get("resolution", "")
            if res:
                cmd += ["-vf", f"scale={res}:-2"]

        if acodec == "copy":
            cmd += ["-c:a", "copy"]
        else:
            cmd += ["-c:a", acodec]
            ab = p.get("abitrate", "128k")
            cmd += ["-b:a", ab]

        cmd.append(out)

    elif job_type == "video_to_gif":
        start = p.get("start", "")
        duration = p.get("duration", "")
        fps = int(p.get("fps", 12))
        width = p.get("width", 480)
        loop = int(p.get("loop", 0))
        optimize = p.get("optimize_palette", True)

        # Place -ss/-t before -i as input options so ffmpeg stops decoding
        # after the requested segment — critical for palettegen which would
        # otherwise scan the entire file before writing any output.
        if start:
            cmd += ["-ss", start]
        if duration:
            cmd += ["-t", duration]
        cmd += ["-i", inp]

        scale_filter = f"fps={fps}"
        if width and str(width) != "0":
            scale_filter += f",scale={width}:-1:flags=lanczos"

        if optimize:
            vf = f"{scale_filter},split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse"
        else:
            vf = scale_filter

        cmd += ["-vf", vf, "-loop", str(loop), out]

    return cmd


def _build_imagemagick_cmd(job_type: str, inp: str, out: str, p: dict) -> list:
    cmd_name = CAPABILITIES.get("imagemagick_cmd") or "convert"
    # modern ImageMagick 7 uses 'magick convert' or just 'magick'
    if cmd_name == "magick":
        base = ["magick"]
    else:
        base = ["convert"]

    if job_type == "image_resize":
        w = p.get("width", "")
        h = p.get("height", "")
        if w and h:
            geometry = f"{w}x{h}"
            if p.get("keep_aspect", True):
                geometry += ">"  # only shrink, keep aspect
        elif w:
            geometry = f"{w}x"
        elif h:
            geometry = f"x{h}"
        else:
            geometry = "1920x1080>"
        return base + [inp, "-resize", geometry, out]

    elif job_type == "image_convert":
        quality = p.get("quality", "")
        cmd = base + [inp]
        if quality:
            cmd += ["-quality", str(quality)]
        strip = p.get("strip_metadata", False)
        if strip:
            cmd += ["-strip"]
        cmd.append(out)
        return cmd

    elif job_type == "image_compress":
        quality = p.get("quality", 85)
        cmd = base + [inp, "-quality", str(quality)]
        strip = p.get("strip_metadata", True)
        if strip:
            cmd += ["-strip"]
        cmd.append(out)
        return cmd

    elif job_type == "image_crop":
        x = p.get("x", 0)
        y = p.get("y", 0)
        w = p.get("w", 100)
        h = p.get("h", 100)
        # +repage removes the virtual canvas offset left by -crop
        return base + [inp, "-crop", f"{w}x{h}+{x}+{y}", "+repage", out]

    return base + [inp, out]


def _build_ytdlp_cmd(job_type: str, url: str, out_dir: str, p: dict) -> list:
    cmd = ["yt-dlp"]

    # Output template
    out_template = str(Path(out_dir) / "%(title)s.%(ext)s")
    cmd += ["-o", out_template]

    # Format selection
    fmt = p.get("format", "")
    quality = p.get("quality", "best")
    if fmt:
        cmd += ["-f", fmt]
    elif quality == "audio":
        cmd += ["-f", "bestaudio", "-x", "--audio-format", p.get("audio_format", "mp3")]
    elif quality == "1080p":
        cmd += ["-f", "bestvideo[height<=1080]+bestaudio[height<=1080]/best[height<=1080]"]
    elif quality == "720p":
        cmd += ["-f", "bestvideo[height<=720]+bestaudio/best[height<=720]"]
    elif quality == "480p":
        cmd += ["-f", "bestvideo[height<=480]+bestaudio/best[height<=480]"]
    else:
        cmd += ["-f", "bestvideo+bestaudio/best"]

    # For split-format downloads (video+audio), merge into mkv to avoid
    # transcoding errors. mkv accepts webm/vp9/opus without re-encoding.
    if quality != "audio" and not fmt:
        cmd += ["--merge-output-format", "mkv"]

    # Subtitles
    if p.get("subtitles"):
        cmd += ["--write-subs", "--write-auto-subs", "--sub-langs", p.get("sub_langs", "all")]

    # Playlist
    if not p.get("playlist", False):
        cmd += ["--no-playlist"]

    # Cookies
    cookies = p.get("cookies_file", "")
    if cookies and Path(cookies).exists():
        cmd += ["--cookies", cookies]

    # Progress: --newline prints each update on its own line instead of \r
    cmd += ["--newline", "--progress"]

    cmd.append(url)
    return cmd


# ── Job runner ────────────────────────────────────────────────────────────────

async def _iter_lines(stream):
    """Read a stream and yield decoded lines split on both \\r and \\n.

    ffmpeg writes progress using \\r (overwrite in-place), so readline() which
    waits for \\n never delivers progress until the process ends.  Reading in
    chunks and splitting on both control characters fixes this.
    """
    buf = b""
    while True:
        chunk = await stream.read(4096)
        if not chunk:
            break
        buf += chunk
        parts = re.split(rb"[\r\n]+", buf)
        buf = parts[-1]
        for part in parts[:-1]:
            line = part.decode("utf-8", errors="replace").strip()
            if line:
                yield line
    if buf:
        line = buf.decode("utf-8", errors="replace").strip()
        if line:
            yield line


async def _run_job(job_id: str, cmd: list):
    job = jobs[job_id]
    job["status"] = "running"
    tool = job.get("tool", "ffmpeg")
    try:
        run_env = None
        if tool == "yt-dlp":
            # yt-dlp is a Python script; without PYTHONUNBUFFERED it buffers
            # stdout when piped, so progress lines don't arrive until process exit.
            run_env = {**os.environ, "PYTHONUNBUFFERED": "1"}

        if tool == "ffmpeg":
            # stdout receives structured -progress pipe:1 output (key=value, newline-
            # terminated). stderr receives the human-readable log (codec info, errors).
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=run_env,
            )
            job["_proc"] = proc

            duration_sec = None

            async def _read_ffmpeg_stderr():
                nonlocal duration_sec
                async for line in _iter_lines(proc.stderr):
                    job["log"].append(line)
                    if duration_sec is None and "Duration:" in line:
                        try:
                            d = line.split("Duration:")[1].split(",")[0].strip()
                            duration_sec = _ts_to_sec(d)
                            job["duration_sec"] = duration_sec
                        except Exception:
                            pass

            async def _read_ffmpeg_progress():
                async for line in _iter_lines(proc.stdout):
                    # -progress pipe:1 emits key=value pairs, one per line
                    if line.startswith("out_time="):
                        try:
                            elapsed = _ts_to_sec(line.split("=", 1)[1])
                            if duration_sec and duration_sec > 0:
                                job["progress"] = min(99, round(elapsed / duration_sec * 100, 1))
                        except Exception:
                            pass
                    elif line.startswith("speed="):
                        job["speed"] = line.split("=", 1)[1].strip()
                    elif line.startswith("fps="):
                        v = line.split("=", 1)[1].strip()
                        if v not in ("0", "0.00", ""):
                            job["fps"] = v

            await asyncio.gather(_read_ffmpeg_stderr(), _read_ffmpeg_progress())
            await proc.wait()

        else:
            # yt-dlp and other tools: merge stderr into stdout
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=run_env,
            )
            job["_proc"] = proc

            async for line in _iter_lines(proc.stdout):
                job["log"].append(line)

                # [download]  45.3% of ~123.45MiB at 2.34MiB/s ETA 00:32
                if "[download]" in line and "%" in line:
                    try:
                        pct_str = re.search(r"(\d+\.?\d*)%", line)
                        if pct_str:
                            job["progress"] = min(99, float(pct_str.group(1)))
                        speed_str = re.search(r"at\s+([\d.]+\w+/s)", line)
                        if speed_str:
                            job["speed"] = speed_str.group(1)
                    except Exception:
                        pass

            await proc.wait()

        if proc.returncode == 0:
            job["status"] = "done"
            job["progress"] = 100
            _persist_completed_output(job)
        elif job["status"] != "cancelled":
            job["status"] = "error"
            # Surface the last ERROR line from the log if available
            error_lines = [l for l in job["log"] if "ERROR" in l or "error" in l.lower()]
            job["error"] = error_lines[-1] if error_lines else f"Exit code {proc.returncode}"

    except Exception as e:
        job["status"] = "error"
        job["error"] = str(e)
        job["log"].append(f"[error] {e}")
    finally:
        job.pop("_proc", None)


def _ts_to_sec(ts: str) -> float:
    ts = ts.strip()
    if ts in ("N/A", ""):
        return 0.0
    parts = ts.split(":")
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    return 0.0


def _mime(path: Path) -> str:
    return {
        ".mp4": "video/mp4", ".m4v": "video/mp4",
        ".mkv": "video/x-matroska", ".webm": "video/webm",
        ".avi": "video/x-msvideo", ".mov": "video/quicktime",
        ".flv": "video/x-flv", ".ts": "video/mp2t",
        ".ogv": "video/ogg",
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".gif": "image/gif",
        ".webp": "image/webp",
    }.get(path.suffix.lower(), "application/octet-stream")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=7860, reload=False)

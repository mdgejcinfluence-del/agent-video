"""Rendu : timeline -> images (Chromium headless) -> MP4 (ffmpeg).

Chaque image est une capture de engine/player.html à un instant t donné.
Les images sont envoyées directement dans ffmpeg (aucun fichier image sur le
disque, mémoire constante). Le rendu est découpé entre plusieurs processus
pour utiliser tous les cœurs.
"""
from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent / "engine"
W, H = 1080, 1920
CHROME_ARGS = ["--no-sandbox", "--disable-dev-shm-usage", "--hide-scrollbars", "--force-color-profile=srgb",
               "--font-render-hinting=none", "--disable-lcd-text"]


def _open(p, timeline):
    browser = p.chromium.launch(args=CHROME_ARGS)
    page = browser.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
    page.goto((ENGINE / "player.html").as_uri())
    report = page.evaluate("tl => window.init(tl)", timeline)
    return browser, page, report


def layout_report(timeline: dict) -> dict:
    """Charge la page sans rien rendre : renvoie les alertes de mise en page."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, _page, report = _open(p, timeline)
        browser.close()
    return report


def still(timeline: dict, t: float, out: str | Path, quality: int = 92) -> str:
    """Une seule image (pour les miniatures et les contrôles)."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, page, _ = _open(p, timeline)
        page.evaluate("t => window.renderAt(t)", t)
        kind = "png" if str(out).endswith(".png") else "jpeg"
        page.screenshot(path=str(out), type=kind, **({} if kind == "png" else {"quality": quality}))
        browser.close()
    return str(out)


def _segment(args):
    timeline_path, f0, f1, fps, out, crf, preset = args
    from playwright.sync_api import sync_playwright
    timeline = json.loads(Path(timeline_path).read_text(encoding="utf-8"))
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "image2pipe", "-vcodec", "mjpeg", "-framerate", str(fps), "-i", "-",
           "-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p", "-r", str(fps),
           "-vf", "scale=in_range=pc:out_range=tv,format=yuv420p", "-color_range", "tv", "-colorspace", "bt709",
           "-color_primaries", "bt709", "-color_trc", "bt709",
           "-g", str(fps * 2), "-bf", "0", "-an", str(out)]
    ff = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    with sync_playwright() as p:
        browser, page, _ = _open(p, timeline)
        try:
            for i in range(f0, f1):
                shot = None
                for essai in range(4):
                    # une capture peut échouer quand la machine manque de mémoire : on réessaie, puis on rouvre le navigateur
                    try:
                        page.evaluate("t => window.renderAt(t)", i / fps)
                        shot = page.screenshot(type="jpeg", quality=94)
                        break
                    except Exception:  # noqa: BLE001
                        if essai == 3:
                            raise
                        time.sleep(0.6 * (essai + 1))
                        if essai >= 1:
                            try:
                                browser.close()
                            except Exception:  # noqa: BLE001
                                pass
                            browser, page, _ = _open(p, timeline)
                ff.stdin.write(shot)
        finally:
            try:
                browser.close()
            except Exception:  # noqa: BLE001
                pass
    ff.stdin.close()
    if ff.wait() != 0:
        raise RuntimeError(f"ffmpeg a échoué sur le segment {f0}-{f1}")
    return str(out)


def render_video(timeline: dict, audio: str | Path | None, out: str | Path, workers: int | None = None,
                 crf: int = 19, preset: str = "veryfast", log=print) -> dict:
    """Rend toute la vidéo. Renvoie {frames, seconds, fps_render}."""
    out = Path(out).resolve(); out.parent.mkdir(parents=True, exist_ok=True)
    audio = str(Path(audio).resolve()) if audio else None
    fps = int(timeline.get("fps", 30))
    n = int(math.ceil(timeline["duration"] * fps))
    workers = workers or max(1, min(4, (os.cpu_count() or 2)))
    tmp = out.parent / f".{out.stem}_tmp"; tmp.mkdir(exist_ok=True)
    tl_path = tmp / "timeline.json"; tl_path.write_text(json.dumps(timeline, ensure_ascii=False), encoding="utf-8")
    bounds = [round(n * k / workers) for k in range(workers + 1)]
    jobs = [(str(tl_path), bounds[k], bounds[k + 1], fps, str(tmp / f"seg{k:02d}.mp4"), crf, preset)
            for k in range(workers) if bounds[k + 1] > bounds[k]]
    t0 = time.time()
    if len(jobs) == 1:
        segs = [_segment(jobs[0])]
    else:
        with ProcessPoolExecutor(max_workers=len(jobs)) as ex:
            segs = list(ex.map(_segment, jobs))
    lst = tmp / "list.txt"; lst.write_text("".join(f"file '{Path(s).name}'\n" for s in segs))
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst)]
    if audio:
        cmd += ["-i", str(audio), "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", "-shortest"]
    else:
        cmd += ["-c:v", "copy"]
    cmd += ["-movflags", "+faststart", str(out)]
    subprocess.run(cmd, check=True, cwd=str(tmp))
    for f in tmp.iterdir():
        f.unlink()
    tmp.rmdir()
    dt = time.time() - t0
    log(f"rendu : {n} images en {dt:.0f} s ({n / dt:.1f} img/s, {len(jobs)} processus)")
    return {"frames": n, "seconds": round(dt, 1), "fps_render": round(n / dt, 1)}


if __name__ == "__main__":
    tl = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    print(render_video(tl, sys.argv[3] if len(sys.argv) > 3 else None, sys.argv[2]))

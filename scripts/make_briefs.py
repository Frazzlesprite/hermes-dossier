r"""Render the two briefs the demo compares, and screenshot them.

Interview and sales on the same Valve evidence. Deterministic: the replay feeds
the same captured pages to both runs.

    python scripts/make_briefs.py
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import demo_valve  # noqa: E402

OUT = Path(tempfile.gettempdir()) / "opencode" / "briefs"
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
PDFTOPPM = (
    r"C:\Users\Headmaster\AppData\Local\Microsoft\WinGet\Packages"
    r"\oschwartz10612.Poppler_Microsoft.Winget.Source_8wekyb3d8bbwe"
    r"\poppler-25.07.0\Library\bin\pdftoppm.exe"
)

RUNS = {
    "interview": "interview for a software engineering role at Valve",
    "sales": "first call with their procurement team",
}


def run(context: str, purpose: str) -> dict:
    os.environ["DOSSIER_CONTEXT"] = context
    os.environ["DOSSIER_PURPOSE"] = purpose
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        demo_valve.main()
    first = demo_valve.LAST["first"]
    return {
        "questions": first["questions"],
        "headline": first["headline"],
        "context_label": first.get("context_label", ""),
        "purpose": first.get("purpose", ""),
        "counts": first["counts"],
    }


def screenshot(html: Path, png: Path) -> None:
    profile = OUT / "edge-profile"
    profile.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            EDGE,
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            f"--user-data-dir={profile}",
            "--virtual-time-budget=4000",
            f"--screenshot={png}",
            "--force-device-scale-factor=2",
            "--window-size=880,900",
            "file:///" + html.as_posix(),
        ],
        capture_output=True,
        timeout=120,
    )


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    results: dict[str, dict] = {}

    for context, purpose in RUNS.items():
        data = run(context, purpose)
        html = Path(tempfile.gettempdir()) / "valve-brief.html"
        target_html = OUT / f"{context}.html"
        target_html.write_text(html.read_text(encoding="utf-8"), encoding="utf-8")
        pdf = Path(tempfile.gettempdir()) / "valve-brief.pdf"
        target_pdf = OUT / f"{context}.pdf"
        target_pdf.write_bytes(pdf.read_bytes())
        if Path(PDFTOPPM).exists():
            subprocess.run(
                [PDFTOPPM, "-png", "-r", "200", "-f", "1", "-l", "1", str(target_pdf), str(OUT / f"{context}-page")],
                capture_output=True,
                timeout=120,
            )
        screenshot(target_html, OUT / f"{context}.png")
        results[context] = data
        print(f"{context}: {len(data['questions'])} questions, png={ (OUT / f'{context}.png').stat().st_size } bytes")

    (OUT / "briefs.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print("wrote", OUT)
    for context, data in results.items():
        print(f"\n{context} ({data['context_label']}):")
        for question in data["questions"]:
            print("   -", question)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

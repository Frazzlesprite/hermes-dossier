from pathlib import Path

p = Path("scripts/make_video_demo.py")
t = p.read_text(encoding="utf-8")

old = 'print(f"wrote {OUT} ({TOTAL:.0f}s, 1920x1080, 30fps, audio)")'
new = 'print(f"wrote {OUT} ({TOTAL:.0f}s, 1280x720, 30fps, audio)")'

if old not in t:
    raise SystemExit("log line not found")
p.write_text(t.replace(old, new), encoding="utf-8")
print("log line fixed")

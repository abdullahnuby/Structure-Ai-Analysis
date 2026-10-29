"""Simple local DXF raster preview; not a scale or engineering check."""

from io import BytesIO
from pathlib import Path
from tempfile import NamedTemporaryFile
import ezdxf, math
from PIL import Image, ImageDraw, ImageFont


def render_dxf_preview_png(
    data: bytes, filename: str = "drawing.dxf", width: int = 1280, height: int = 900
) -> bytes:
    with NamedTemporaryFile(suffix=".dxf", delete=False) as f:
        f.write(data)
        p = Path(f.name)
    try:
        doc = ezdxf.readfile(p)
    finally:
        p.unlink(missing_ok=True)
    es = list(doc.modelspace())
    if not es:
        raise ValueError("DXF has no entities.")
    pts = []
    for e in es:
        try:
            if e.dxftype() == "LINE":
                pts.extend([[e.dxf.start.x, e.dxf.start.y], [e.dxf.end.x, e.dxf.end.y]])
            elif e.dxftype() in {"LWPOLYLINE", "POLYLINE"}:
                pts.extend(
                    [
                        [p[0], p[1]]
                        for p in (
                            e.get_points("xy")
                            if e.dxftype() == "LWPOLYLINE"
                            else [v.dxf.location for v in e.vertices]
                        )
                    ]
                )
            elif e.dxftype() in {"TEXT", "MTEXT", "ATTRIB", "ATTDEF"}:
                pts.append([e.dxf.insert.x, e.dxf.insert.y])
        except Exception:
            pass
    if not pts:
        raise ValueError("No supported geometry for preview.")
    mnx, maxx = min(float(p[0]) for p in pts), max(float(p[0]) for p in pts)
    mny, maxy = min(float(p[1]) for p in pts), max(float(p[1]) for p in pts)
    if maxx - mnx < 1e-9:
        maxx = mnx + 1
    if maxy - mny < 1e-9:
        maxy = mny + 1
    s = min((width - 70) / (maxx - mnx), (height - 100) / (maxy - mny))
    img = Image.new("RGB", (width, height), "white")
    d = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    d.text((25, 20), f"DXF PREVIEW - {Path(filename).name[:80]}", fill="#22313f", font=font)

    def px(p):
        return int(35 + (float(p[0]) - mnx) * s), int(45 + (maxy - float(p[1])) * s)

    palette = ["#202a35", "#286c8e", "#9b5b24", "#4f7d51", "#8064a2", "#9a4b59"]
    layers = sorted({str(e.dxf.get("layer", "0")) for e in es})
    colors = {n: palette[i % len(palette)] for i, n in enumerate(layers)}
    for e in es[:25000]:
        k = e.dxftype()
        ln = str(e.dxf.get("layer", "0"))
        color = colors.get(ln, "#222")
        q = []
        try:
            if k == "LINE":
                q = [px(e.dxf.start), px(e.dxf.end)]
            elif k == "LWPOLYLINE":
                q = [px(p) for p in e.get_points("xy")]
                if e.closed and q:
                    q.append(q[0])
            elif k == "POLYLINE":
                q = [px(v.dxf.location) for v in e.vertices]
                if e.is_closed and q:
                    q.append(q[0])
            elif k in {"TEXT", "MTEXT", "ATTRIB", "ATTDEF"}:
                d.text(px(e.dxf.insert), str(e.dxf.get("text", ""))[:60], fill=color, font=font)
            elif k == "CIRCLE":
                c = e.dxf.center
                r = float(e.dxf.radius) * s
                x, y = px(c)
                d.ellipse((x - r, y - r, x + r, y + r), outline=color)
        except Exception:
            continue
        if len(q) > 1:
            try:
                d.line(q, fill=color, width=2)
            except Exception:
                pass
    d.text(
        (25, height - 25),
        "VISUAL AID ONLY — NOT TO SCALE — REVIEW ORIGINAL CAD",
        fill="#a12828",
        font=font,
    )
    o = BytesIO()
    img.save(o, format="PNG")
    return o.getvalue()

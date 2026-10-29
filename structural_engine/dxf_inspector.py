"""Read-only DXF metadata inspection."""

from pathlib import Path
from tempfile import NamedTemporaryFile
from collections import Counter
import ezdxf
from ezdxf import bbox


def inspect_dxf_bytes(data: bytes, filename: str = "drawing.dxf"):
    if not data:
        raise ValueError("DXF file is empty.")
    with NamedTemporaryFile(suffix=".dxf", delete=False) as f:
        f.write(data)
        p = Path(f.name)
    try:
        doc = ezdxf.readfile(p)
    except Exception as e:
        raise ValueError(f"Invalid DXF: {e}") from e
    finally:
        p.unlink(missing_ok=True)
    types = Counter()
    layers = Counter()
    for e in doc.modelspace():
        types[e.dxftype()] += 1
        layers[str(e.dxf.get("layer", "0"))] += 1
    ext = None
    try:
        b = bbox.extents(doc.modelspace(), fast=True)
        if b.has_data:
            ext = {
                "min_x": float(b.extmin.x),
                "min_y": float(b.extmin.y),
                "max_x": float(b.extmax.x),
                "max_y": float(b.extmax.y),
                "width": float(b.extmax.x - b.extmin.x),
                "height": float(b.extmax.y - b.extmin.y),
            }
    except Exception:
        pass
    return {
        "filename": Path(filename).name,
        "dxf_version": doc.dxfversion,
        "modelspace_entity_count": sum(types.values()),
        "entity_counts": dict(types),
        "layers": [{"name": n, "entity_count": v} for n, v in sorted(layers.items())],
        "extents": ext,
        "units_code": int(doc.header.get("$INSUNITS", 0) or 0),
        "warnings": [
            "هذا فحص إحصائي فقط ولا يحدد الوظيفة الإنشائية تلقائيًا.",
            "يجب تأكيد الوحدة والأبعاد يدويًا.",
        ],
    }

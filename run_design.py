"""Run a design from a JSON file:  python run_design.py examples/design/beam_3span.json

Writes <out>/<name>.json and <out>/<name>.md (default folder: output/design) and prints a summary.
Exit code: 0 = design OK, 1 = design failed or not possible, 2 = invalid input.
All results are NOT FOR CONSTRUCTION and use UNVERIFIED design-code parameters (see the report).
"""

import argparse
import json
import re
import sys
from pathlib import Path

from structural_engine.design import run_design
from structural_engine.design.params import STATUS_BANNER
from structural_engine.design.report import to_markdown


def _summary(r):
    lines = [f"{r['name']}  [{r['type']}]  ->  {r['status']}"]
    if r["type"] == "continuous_beam":
        for s in r["spans"]:
            lines.append(
                f"  span {s['index']}: sagging {s['sagging'].get('bars') or s['sagging'].get('reason')}"
            )
        for s in r["supports"]:
            lines.append(
                f"  support {s['index']}: top {s['hogging'].get('bars') or s['hogging'].get('reason')}"
            )
    elif r["type"] == "slab_strip":
        for s in r["spans"]:
            lines.append(
                f"  span {s['index']}: bottom {s['sagging'].get('bars') or s['sagging'].get('reason')}"
            )
        for s in r["supports"]:
            lines.append(
                f"  support {s['index']}: top {s['hogging'].get('bars') or s['hogging'].get('reason')}"
            )
    elif r["type"] == "floor":
        lines.append(
            f"  {len(r['columns'])} columns, {len(r['beams'])} beams, {len(r['slabs'])} slab panels; "
            f"load check {r['equilibrium']['difference_pct']:.3f} %"
        )
        for cid, c in r["columns"].items():
            res = c["design"].get("result") or {}
            lines.append(
                f"  {cid}: Pu {c['Pu_kN']:.0f} kN -> {res.get('bars', c['design']['status'])}"
            )
        for bid, b in r["beams"].items():
            lines.append(f"  {bid}: {b['design']['status']}")
    else:
        res = r.get("result") or {}
        lines.append(
            f"  bars {res.get('bars', '-')}, ratio {res.get('ratio', float('nan')):.2f}"
            if res
            else "  no layout"
        )
    for f in r.get("failures") or []:
        lines.append(f"  ! {f}")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("spec", help="JSON design input")
    ap.add_argument("--out", default="output/design", help="output folder")
    args = ap.parse_args(argv)
    try:
        spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
        result = run_design(spec)
    except (OSError, ValueError, KeyError) as exc:
        print(f"Invalid input: {exc!r}", file=sys.stderr)
        return 2
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stem = re.sub(r"[^\w\-]+", "_", result["name"]).strip("_") or "design"
    (out / f"{stem}.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out / f"{stem}.md").write_text(to_markdown(result), encoding="utf-8")
    print(STATUS_BANNER)
    print(_summary(result))
    print(f"report: {out / (stem + '.md')}")
    return 0 if result["status"] == "OK" else 1


if __name__ == "__main__":
    sys.exit(main())

"""Shared fixtures: small synthetic DXF drawings built in memory (no real project data)."""

from __future__ import annotations

import io

import ezdxf
import pytest


def _to_bytes(doc) -> bytes:
    buffer = io.StringIO()
    doc.write(buffer)
    return buffer.getvalue().encode("utf-8")


def _rect(x, y, w, h):
    return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]


@pytest.fixture
def sample_dxf_bytes() -> bytes:
    """Drawing in millimetres with five 'column' entities of different kinds.

    - closed LWPOLYLINE 600x300 on layer 'column 60x30cm'
    - block INSERT of a 400x400 square on 'column 40x40'
    - CIRCLE of diameter 500 on 'column 50x50'
    - two loose LINEs on 'column 30x30'
    plus a title text and an unmapped layer.
    """
    doc = ezdxf.new("R2018")
    msp = doc.modelspace()
    for name in ("column 60x30cm", "column 40x40", "column 50x50", "column 30x30", "TEXT", "misc"):
        doc.layers.add(name)
    msp.add_lwpolyline(_rect(0, 0, 600, 300), close=True, dxfattribs={"layer": "column 60x30cm"})
    block = doc.blocks.new("C40")
    block.add_lwpolyline(_rect(0, 0, 400, 400), close=True)
    msp.add_blockref("C40", (2000, 0), dxfattribs={"layer": "column 40x40"})
    msp.add_circle((4000, 250), 250, dxfattribs={"layer": "column 50x50"})
    msp.add_line((6000, 0), (6300, 0), dxfattribs={"layer": "column 30x30"})
    msp.add_line((6300, 0), (6300, 300), dxfattribs={"layer": "column 30x30"})
    msp.add_text("GROUND FLOOR PLAN", dxfattribs={"layer": "TEXT", "insert": (0, -1000)})
    msp.add_line((0, 2000), (1000, 2000), dxfattribs={"layer": "misc"})
    return _to_bytes(doc)


@pytest.fixture
def make_dxf():
    """Factory: make_dxf(lambda doc, msp: ...) -> bytes."""

    def build(fill) -> bytes:
        doc = ezdxf.new("R2018")
        fill(doc, doc.modelspace())
        return _to_bytes(doc)

    return build

"""Create a toy architectural DXF fixture used by the end-to-end acceptance test."""
from pathlib import Path
import ezdxf
out=Path(__file__).with_name("demo_architecture.dxf")
doc=ezdxf.new("R2013"); doc.units=ezdxf.units.MM
doc.layers.new("A-WALL",dxfattribs={"color":7}); doc.layers.new("A-GRID",dxfattribs={"color":8,"linetype":"DASHED"}); doc.layers.new("A-DOOR",dxfattribs={"color":3})
msp=doc.modelspace(); msp.add_lwpolyline([(0,0),(8000,0),(8000,10000),(0,10000),(0,0)],close=False,dxfattribs={"layer":"A-WALL"})
for x in (0,4000,8000): msp.add_line((x,0),(x,10000),dxfattribs={"layer":"A-GRID"})
for y in (0,5000,10000): msp.add_line((0,y),(8000,y),dxfattribs={"layer":"A-GRID"})
msp.add_line((0,2500),(0,3400),dxfattribs={"layer":"A-DOOR"}); doc.saveas(out); print(out)

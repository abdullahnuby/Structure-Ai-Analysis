"""Create a DXF example that follows the agreed architectural intake layer standard."""
from pathlib import Path
import ezdxf
OUT = Path(__file__).with_name("architectural_standard_demo.dxf")
doc = ezdxf.new("R2013")
doc.units = ezdxf.units.MM
doc.header["$INSUNITS"] = 4
for name, colour in {"TEXT":7,"wall 25 cm":8,"wall 12 cm":9,"column 60x30":1,"beam 30x60":5,"slab":3,"opening":4,"dimension":2}.items():
    doc.layers.new(name, dxfattribs={"color": colour})
msp = doc.modelspace()
msp.add_lwpolyline([(0,0),(8000,0),(8000,6000),(0,6000)],close=True,dxfattribs={"layer":"slab"})
xs=[600,4000,7400]; ys=[300,3000,5700]
for x in xs:
  for y in ys: msp.add_lwpolyline([(x-300,y-150),(x+300,y-150),(x+300,y+150),(x-300,y+150)],close=True,dxfattribs={"layer":"column 60x30"})
for y in ys:
  for x1,x2 in zip(xs,xs[1:]): msp.add_line((x1,y),(x2,y),dxfattribs={"layer":"beam 30x60"})
for x in xs:
  for y1,y2 in zip(ys,ys[1:]): msp.add_line((x,y1),(x,y2),dxfattribs={"layer":"beam 30x60"})
msp.add_lwpolyline([(0,0),(8000,0),(8000,250)],close=False,dxfattribs={"layer":"wall 25 cm"})
msp.add_lwpolyline([(4000,300),(4000,5700)],close=False,dxfattribs={"layer":"wall 12 cm"})
msp.add_line((1800,0),(2700,0),dxfattribs={"layer":"opening"})
msp.add_text("GROUND FLOOR PLAN",dxfattribs={"layer":"TEXT","height":180}).set_placement((4000,-650))
msp.add_text("Scale 1:100",dxfattribs={"layer":"dimension","height":100}).set_placement((7000,-900))
doc.saveas(OUT); print(OUT)

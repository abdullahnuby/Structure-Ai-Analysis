"""Mesh-convergence benchmark for the planar Q4 shell/plate prototype."""
from __future__ import annotations
import csv, json
from pathlib import Path
import argparse
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from structural_engine.plate_shell import build_rectangular_plate_model, analyze_plate_shell, simply_supported_square_plate_reference

def main() -> int:
    p=argparse.ArgumentParser(description="Mesh-convergence benchmark against the Navier thin-square-plate reference."); p.add_argument("--out",default="output/plate_shell_benchmark"); args=p.parse_args()
    out=Path(args.out); out.mkdir(parents=True,exist_ok=True); L=4.0; q=1.0; E=30000.0; t=0.04; nu=0.2; reference=simply_supported_square_plate_reference(L,q,E,t,nu,terms=101); rows=[]
    for n in (2,4,6,8,12):
        model=build_rectangular_plate_model(Lx_m=L,Ly_m=L,nx=n,ny=n,thickness_m=t,E_MPa=E,nu=nu,pressure_kN_m2=q,support_type="simply_supported"); r=analyze_plate_shell(model)
        center=min(r["nodes"],key=lambda x:(x["x_m"]-L/2)**2+(x["y_m"]-L/2)**2); w=abs(float(center["uz_m"]))
        rows.append({"mesh_nx":n,"mesh_ny":n,"nodes":r["mesh"]["node_count"],"elements":r["mesh"]["element_count"],"center_deflection_mm":w*1000,"navier_reference_mm":reference["center_deflection_m"]*1000,"relative_error_percent":100*(w-reference["center_deflection_m"])/reference["center_deflection_m"],"sum_Fz_kN":r["equilibrium"]["sum_Fz_kN"],"relative_free_dof_residual":r["equilibrium"]["relative_free_dof_residual"]})
    with (out/"plate_shell_mesh_convergence.csv").open("w",newline="",encoding="utf-8-sig") as f: writer=csv.DictWriter(f,fieldnames=list(rows[0].keys())); writer.writeheader(); writer.writerows(rows)
    payload={"benchmark":"SS square plate under uniform pressure, thin-plate Kirchhoff-Love/Navier reference","inputs":{"side_m":L,"pressure_kN_m2":q,"E_MPa":E,"thickness_m":t,"nu":nu},"reference":reference,"results":rows,"acceptance":{"12x12_relative_absolute_error_percent_max":0.2,"all_equilibrium_abs_sum_Fz_kN_max":1e-7},"status":"PASS" if abs(rows[-1]["relative_error_percent"])<=0.2 and all(abs(x["sum_Fz_kN"])<=1e-7 for x in rows) else "FAIL","limitations":["Benchmark validates only a linear-elastic simply-supported square plate in the stated thin-plate regime.","It does not validate arbitrary shell geometry, flat-slab support regions, punching shear, RC resistance/serviceability, code load combinations or reinforcement design."]}
    (out/"plate_shell_benchmark.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    styles=getSampleStyleSheet(); styles.add(ParagraphStyle(name="BenchmarkTitle",parent=styles["Title"],fontSize=14,leading=17,alignment=1,textColor=colors.HexColor("#17324D")))
    doc=SimpleDocTemplate(str(out/"plate_shell_benchmark_report.pdf"),pagesize=landscape(A4),rightMargin=10*mm,leftMargin=10*mm,topMargin=10*mm,bottomMargin=10*mm)
    story=[Paragraph("STRUCTURAL STUDIO — PLATE/SHELL MESH CONVERGENCE BENCHMARK",styles["BenchmarkTitle"]),Spacer(1,3*mm),Paragraph(f"Square plate {L:g} x {L:g} m; q={q:g} kN/m²; E={E:g} MPa; t={t:g} m; nu={nu:g}; simple supports.",styles["BodyText"]),Spacer(1,2*mm),Paragraph(f"Navier reference: {reference['center_deflection_m']*1000:.6f} mm | reference coefficient: {reference['normalized_deflection_coefficient']:.8f} | benchmark status: {payload['status']}",styles["BodyText"]),Spacer(1,3*mm)]
    table=[["Mesh","Nodes","Q4 elements","Center uz (mm)","Reference (mm)","Error (%)","ΣFz (kN)","Free residual"]]
    for x in rows: table.append([f"{x['mesh_nx']}x{x['mesh_ny']}",x["nodes"],x["elements"],f"{x['center_deflection_mm']:.6f}",f"{x['navier_reference_mm']:.6f}",f"{x['relative_error_percent']:.3f}",f"{x['sum_Fz_kN']:.2e}",f"{x['relative_free_dof_residual']:.2e}"])
    t=Table(table,repeatRows=1,colWidths=[22*mm,20*mm,27*mm,32*mm,32*mm,23*mm,27*mm,30*mm]); t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#17324D")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("GRID",(0,0),(-1,-1),.35,colors.grey),("FONTSIZE",(0,0),(-1,-1),8),("ALIGN",(0,0),(-1,-1),"CENTER"),("VALIGN",(0,0),(-1,-1),"MIDDLE")]))
    story.extend([t,Spacer(1,4*mm),Paragraph("Scope: this benchmark is a verification fixture for one simply-supported thin square plate. It does not establish general shell qualification or any ECP 203-2025 resistance/serviceability, punching, or reinforcement design validity. Not for construction.",styles["BodyText"])]); doc.build(story)
    print(f"Benchmark {payload['status']}; reference={reference['center_deflection_m']*1000:.6f} mm; 12x12 error={rows[-1]['relative_error_percent']:.3f}%"); print(f"CSV: {out/'plate_shell_mesh_convergence.csv'}\nPDF: {out/'plate_shell_benchmark_report.pdf'}\nJSON: {out/'plate_shell_benchmark.json'}")
    return 0 if payload["status"]=="PASS" else 1
if __name__=="__main__": raise SystemExit(main())
from io import BytesIO
from xml.sax.saxutils import escape
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph
from .workorder import build_steps


def paragraph(pdf, text, x, y, width, size=9):
    p = Paragraph(escape(text), ParagraphStyle('text', fontName='Helvetica', fontSize=size, leading=size*1.25))
    _, height = p.wrap(width, 10000)
    p.drawOn(pdf, x, y-height)
    return y-height-6


def cross_section(pdf, position, x, y, width=210, height=100):
    points = position['contour']['points']
    scale = min(width/max(w for _,w in points), height/points[-1][0])
    path = pdf.beginPath()
    outline = [(-w/2,z) for z,w in points] + [(w/2,z) for z,w in reversed(points)]
    for i,(a,z) in enumerate(outline):
        (path.moveTo if i==0 else path.lineTo)(x+width/2+a*scale,y+z*scale)
    path.close()
    pdf.setStrokeColorRGB(.2,.25,.3)
    pdf.drawPath(path)
    pdf.setStrokeColorRGB(.4,.55,.65)
    for b in position['boxes']:
        pdf.rect(x+width/2+b['x']*scale,y+b['z']*scale,b['dx']*scale,b['dz']*scale)


def layer_plans(pdf, position, top):
    layers = position['layers']
    rows = (len(layers)+2)//3
    cell_h = min(88, 240/max(1, rows))
    for i, layer in enumerate(layers):
        x, y = 38+(i%3)*175, top-(i//3+1)*cell_h
        pdf.setFont('Helvetica',6)
        pdf.drawString(x,y+cell_h-8,f"Layer {layer['no']} · looking down · forward ↑")
        bs = [b for b in position['boxes'] if b['layer']==layer['no']]
        full_w = max(w for _,w in position['contour']['points'])
        scale = min(160/full_w,(cell_h-15)/position['length'])
        for b in bs:
            bx = x+80+b['x']*scale
            by = y+(position['length']/2-b['y']-b['dy'])*scale
            pdf.rect(bx,by,b['dx']*scale,b['dy']*scale)
            pdf.setFont('Helvetica',min(6,b['dy']*scale*.4))
            pdf.drawCentredString(bx+b['dx']*scale/2,by+b['dy']*scale/2,str(b['slot']))


def workorder_pdf(plan, result, positions):
    stream = BytesIO()
    pdf = canvas.Canvas(stream,pagesize=A4)
    pdf.setTitle(f'{plan.name} — load work order')
    pdf.setFont('Helvetica-Bold',20)
    pdf.drawString(36,802,'Cargo load work order')
    m = plan.manifest
    y = paragraph(pdf,f'{plan.name} | Team leader: {m.leader} | Flight: {m.flight} | Registration: {m.registration} | Date: {m.date}',36,780,523)
    pdf.setFont('Helvetica-Bold',8)
    pdf.drawString(36,y-10,'DECK / POSITION       BOXES       ACTUAL KG       CHARGEABLE KG       HEIGHT CM       ARM M (EST.)')
    y -= 25
    row_h = min(16,370/max(1,len(positions)))
    for p in positions:
        pdf.setFont('Helvetica',min(8,row_h*.65))
        values = [f"{p['deck']} {p['position']}",str(len(p['boxes'])),f"{p['kg']:.1f}",f"{p['totals']['chargeable_kg']:.1f}",f"{p['height']:.1f}",str(p['arm'] if p['arm'] is not None else 'Missing')]
        for x, value in zip([36,145,210,310,420,510],values):
            pdf.drawString(x,y,value)
        y -= row_h
    y = paragraph(pdf,f"Scope totals: {sum(len(p['boxes']) for p in positions)} boxes; {sum(p['kg'] for p in positions):.1f} kg actual; {sum(p['totals']['chargeable_kg'] for p in positions):.1f} kg chargeable.",36,y-10,523)
    wb = result['wb']
    y = paragraph(pdf,f"Whole-aircraft W&B: centroid {wb['centroid_m']} m; zero-fuel CG {wb['cg_pct_mac']}% MAC. {wb['status']}. {wb['note']} {'; '.join(wb['warnings'])}",36,y,523)
    y = paragraph(pdf,'Notes: '+m.notes,36,y,523)
    paragraph(pdf,'Team leader signature: ____________________      Load control check: ____________________',36,min(y-20,100),523)
    for p in positions:
        pdf.showPage()
        pdf.setFont('Helvetica-Bold',16)
        pdf.drawString(36,808,f"{p['deck'].upper()} {p['position']} — {len(p['boxes'])} boxes")
        paragraph(pdf,f"{p['uld']} | {p['contour']['name']} | Geometry and arms: planning estimates. {p['kg']:g} kg actual / {p['totals']['chargeable_kg']:g} kg chargeable",36,791,523)
        cross_section(pdf,p,175,650)
        steps = build_steps(p)
        # Keep one page per position; scale the complete instructions to available space.
        size = 8.0
        texts = [f'{i+1}. {s}' for i,s in enumerate(steps)]
        while size > 2:
            heights = [Paragraph(escape(t),ParagraphStyle('measure',fontSize=size,leading=size*1.25)).wrap(523,10000)[1]+6 for t in texts]
            if sum(heights) <= 350:
                break
            size -= .25
        y = 635
        for text in texts:
            y = paragraph(pdf,text,36,y,523,size)
        layer_plans(pdf,p,min(y-8,275))
    pdf.save()
    return stream.getvalue()

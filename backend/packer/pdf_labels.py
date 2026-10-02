from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, A4
from reportlab.graphics.barcode.code128 import Code128


def labels_pdf(plan, boxes, format):
    stream = BytesIO()
    if format == 'letter10':
        page, cols, rows, w, h, left, top, gap = letter, 2, 5, 288, 144, 11.25, 36, 13.5
    elif format == 'a4-8':
        page, cols, rows, w, h, left, top, gap = A4, 2, 4, 281, 192, 16, 37, 0
    else:
        page, cols, rows, w, h, left, top, gap = (432, 288), 1, 1, 432, 288, 0, 0, 0
    pdf = canvas.Canvas(stream, pagesize=page)
    pdf.setTitle(f'{plan.name} — box labels')
    for i, box in enumerate(boxes):
        if i and i % (cols*rows) == 0:
            pdf.showPage()
        index = i % (cols*rows)
        x, y = left+(index % cols)*(w+gap), page[1]-top-(index//cols+1)*h
        pdf.setStrokeColorRGB(.75,.75,.75)
        pdf.rect(x,y,w,h)
        title = f"{'MD' if box['deck']=='main' else 'LWR'} {box['position']}   {box['box_id']}"
        pdf.setFont('Helvetica-Bold', min(17,(w-16)/pdf.stringWidth(title,'Helvetica-Bold',1)))
        pdf.drawString(x+8,y+h-21,title)
        lines = [f"{box['deck']} deck · Layer {box['layer']} · Slot {box['slot']}", box['aircraft'],
                 f"{box['box_type']} · {box['dims_cm']} cm" + (' · THIS SIDE UP' if box['upright'] else ''),
                 f"Actual {box['actual_kg']:g} / Volume {box['volume_kg']:g} / Chargeable {box['chargeable_kg']:g} kg",
                 f"{plan.name} · Flight {plan.manifest.flight}"]
        for line_no, line in enumerate(lines):
            size = min(8, (w-16)/max(pdf.stringWidth(line, 'Helvetica', 1),1))
            pdf.setFont('Helvetica',size)
            pdf.drawString(x+8,y+h-34-line_no*11,line)
        barcode = Code128(box['box_id'], barHeight=27, barWidth=.75, humanReadable=True)
        pdf.saveState()
        pdf.translate(x+8,y+8)
        pdf.scale(min(1,(w-16)/barcode.width),1)
        barcode.drawOn(pdf,0,0)
        pdf.restoreState()
    pdf.save()
    return stream.getvalue()

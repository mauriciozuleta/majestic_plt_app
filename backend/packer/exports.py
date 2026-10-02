import csv
from io import StringIO


def boxes_csv(boxes):
    stream = StringIO()
    columns = ['box_id','aircraft','deck','uld','position','layer','slot','box_type','dims_cm',
               'x_cm','y_cm','z_cm','across_cm','along_cm','height_cm','actual_kg','volume_kg','chargeable_kg']
    writer = csv.DictWriter(stream, fieldnames=columns)
    writer.writeheader()
    for box in boxes:
        row = {key: box.get(key, '') for key in columns}
        row.update({out: box[key] for out, key in zip(columns[9:15], ['x','y','z','dx','dy','dz'])})
        # Prevent a catalogue/manifest value from becoming a spreadsheet formula.
        writer.writerow({k: "'"+v if isinstance(v, str) and v.startswith(('=', '+', '-', '@')) else v for k, v in row.items()})
    return stream.getvalue()

import os, csv
from pathlib import Path
import redact

# Ensure delete labels and safety sweep are set so redact will populate LOW_CONF_CANDIDATES
os.environ['DELETE_LABELS'] = 'EMAIL,PHONE,SSN,DOB,ADDRESS,PERSON'
# optionally enable safety sweep
os.environ['REDACT_SAFETY_SWEEP'] = '1'

INDIR = Path('emails_folder/Spam/test_emails/generated_emails_bulk_long')
files = sorted(INDIR.glob('*.txt'))

# Clear any existing low-conf list
redact.LOW_CONF_CANDIDATES.clear()

for p in files:
    text = p.read_text(encoding='utf-8', errors='ignore')
    # call redact to populate LOW_CONF_CANDIDATES; we only need spans returned
    _out, spans = redact.redact(text, {}, source_name=p.name, return_spans=True)

# Dump LOW_CONF_CANDIDATES to CSV
out_csv = Path('low_confidence_audit.csv')
with out_csv.open('w', newline='', encoding='utf-8') as fh:
    writer = csv.writer(fh)
    writer.writerow(['source_file','label','start','end','score','snippet','source'])
    for rec in redact.LOW_CONF_CANDIDATES:
        writer.writerow(rec)

print('Wrote', out_csv)

import os, re, hashlib
from pathlib import Path
import redact

# Ensure per-label deletion for all PII labels for this verification run
os.environ['DELETE_LABELS'] = 'EMAIL,PHONE,SSN,DOB,ADDRESS,PERSON'
# redact.get_delete_labels() reads env each call; ensure redact module will see it

INDIR = Path('emails_folder/Spam/test_emails/generated_emails_bulk_long')
files = sorted(INDIR.glob('*.txt'))

labels = ['EMAIL', 'PHONE', 'SSN', 'DOB', 'ADDRESS', 'PERSON']
baseline = {l: 0 for l in labels}
replaced = {l: 0 for l in labels}
per_file = {}

# helpers from redact module
EMAIL = redact.EMAIL
OBFUSCATED_EMAIL = getattr(redact, 'OBFUSCATED_EMAIL', None)
PHONE = redact.PHONE
SSN_STRICT = redact.SSN_STRICT
SSN_LOOSE = redact.SSN_LOOSE
DOB = redact.DOB
ADDRESS = redact.ADDRESS
ADDRESS_LOOSE = redact.ADDRESS_LOOSE
FALLBACK_NAME_MULTI = redact.FALLBACK_NAME_MULTI
FALLBACK_NAME_SINGLE_LINE = redact.FALLBACK_NAME_SINGLE_LINE
nlp = getattr(redact, 'nlp', None)

for p in files:
    try:
        text = p.read_text(encoding='utf-8', errors='ignore')
    except Exception as e:
        print('Could not read', p, e)
        continue
    file_base = p.name
    per_file[file_base] = {'baseline': {l:0 for l in labels}, 'replaced': {l:0 for l in labels}}

    # baseline counts: regex-based
    per_file[file_base]['baseline']['EMAIL'] += len(EMAIL.findall(text))
    if OBFUSCATED_EMAIL is not None:
        per_file[file_base]['baseline']['EMAIL'] += len(OBFUSCATED_EMAIL.findall(text))
    per_file[file_base]['baseline']['PHONE'] += len(PHONE.findall(text))
    per_file[file_base]['baseline']['SSN'] += len(SSN_STRICT.findall(text))
    # SSN_LOOSE only when 'ssn' cue nearby
    for m in SSN_LOOSE.finditer(text):
        ctx = text[max(0,m.start()-30):m.end()+10].lower()
        if 'ssn' in ctx:
            per_file[file_base]['baseline']['SSN'] += 1
    # DOB - use DOB regex but skip timestamps if time follows
    for m in DOB.finditer(text):
        is_iso = re.match(r"^(?:19|20)\d{2}[\/-]", m.group(0))
        if is_iso:
            look = text[m.end():m.end()+10]
            if re.match(r"^\s*\d{1,2}:\d{2}(?::\d{2})?", look):
                continue
        per_file[file_base]['baseline']['DOB'] += 1
    per_file[file_base]['baseline']['ADDRESS'] += len(ADDRESS.findall(text))
    per_file[file_base]['baseline']['ADDRESS'] += len(ADDRESS_LOOSE.findall(text))
    # PERSON via spaCy NER + fallbacks
    pn = 0
    if nlp:
        doc = nlp(text)
        for ent in doc.ents:
            if ent.label_ == 'PERSON':
                pn += 1
    pn += len(FALLBACK_NAME_MULTI.findall(text))
    pn += len(FALLBACK_NAME_SINGLE_LINE.findall(text))
    per_file[file_base]['baseline']['PERSON'] = pn

    # Now call redact.redact to get replaced counts via stats dict
    stats = {}
    # Ensure runtime delete labels read from env
    os.environ['DELETE_LABELS'] = 'EMAIL,PHONE,SSN,DOB,ADDRESS,PERSON'
    out = redact.redact(text, stats, source_name=file_base)
    # extract counts recorded in stats
    per_file[file_base]['replaced']['ADDRESS'] = stats.get('ADDRESS_REPLACED', 0)
    per_file[file_base]['replaced']['PERSON'] = stats.get('PERSON_REPLACED', 0)
    per_file[file_base]['replaced']['EMAIL'] = stats.get('EMAIL_REPLACED', 0)
    per_file[file_base]['replaced']['PHONE'] = stats.get('PHONE_REPLACED', 0)
    per_file[file_base]['replaced']['SSN'] = stats.get('SSN_REPLACED', 0)
    per_file[file_base]['replaced']['DOB'] = stats.get('DOB_REPLACED', 0)

    # aggregate
    for l in labels:
        baseline[l] += per_file[file_base]['baseline'][l]
        replaced[l] += per_file[file_base]['replaced'][l]

# Print summary
print('Files checked:', len(per_file))
print('\nOverall baseline counts:')
for l in labels:
    print(f"{l}: {baseline[l]}")

print('\nOverall replaced counts (from redact stats):')
for l in labels:
    print(f"{l}: {replaced[l]}  ({(replaced[l]/baseline[l]*100) if baseline[l]>0 else 0:.1f}% of baseline)")

# list files with any misses (baseline > replaced) for inspection
misses = {f: {l: (per_file[f]['baseline'][l], per_file[f]['replaced'][l]) for l in labels if per_file[f]['baseline'][l] > per_file[f]['replaced'][l]} for f in per_file}
miss_files = {f:misses[f] for f in misses if misses[f]}
print('\nFiles with potential misses (baseline > replaced):', len(miss_files))
for f, data in list(miss_files.items())[:20]:
    print('\nFile:', f)
    for l,(b,r) in data.items():
        print(f"  {l}: baseline={b}, replaced={r}")

# report done
print('\nCoverage check complete.')

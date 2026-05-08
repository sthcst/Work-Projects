import os, re
from pathlib import Path
import redact

# Use phonenumbers-based baseline for phones so selected_pct is comparable
try:
    import phonenumbers
except Exception:
    phonenumbers = None

INDIR = Path('emails_folder/Spam/test_emails/generated_emails_bulk_long')
files = sorted(INDIR.glob('*.txt'))

labels = ['EMAIL', 'PHONE', 'SSN', 'DOB', 'ADDRESS', 'PERSON']
baseline = {l: 0 for l in labels}
selected = {l: 0 for l in labels}

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

    # baseline candidate counts
    baseline['EMAIL'] += len(EMAIL.findall(text))
    if OBFUSCATED_EMAIL is not None:
        baseline['EMAIL'] += len(OBFUSCATED_EMAIL.findall(text))

    # phone baseline using phonenumbers when available
    if phonenumbers is not None:
        cnt = 0
        for match in phonenumbers.PhoneNumberMatcher(text, None):
            try:
                pn = match.number
                nsn = phonenumbers.national_significant_number(pn)
                if len(re.sub(r'\D', '', nsn)) >= 7:
                    cnt += 1
            except Exception:
                continue
        baseline['PHONE'] += cnt
    else:
        baseline['PHONE'] += len(PHONE.findall(text))

    baseline['SSN'] += len(SSN_STRICT.findall(text))
    for m in SSN_LOOSE.finditer(text):
        ctx = text[max(0,m.start()-30):m.end()+10].lower()
        if 'ssn' in ctx:
            baseline['SSN'] += 1
    for m in DOB.finditer(text):
        is_iso = re.match(r"^(?:19|20)\d{2}[\/ -]", m.group(0))
        if is_iso:
            look = text[m.end():m.end()+10]
            if re.match(r"^\s*\d{1,2}:\d{2}(?::\d{2})?", look):
                continue
        baseline['DOB'] += 1
    baseline['ADDRESS'] += len(ADDRESS.findall(text))
    baseline['ADDRESS'] += len(ADDRESS_LOOSE.findall(text))
    # PERSON baseline via NER + fallbacks
    pn = 0
    if nlp:
        doc = nlp(text)
        for ent in doc.ents:
            if ent.label_ == 'PERSON':
                pn += 1
    pn += len(FALLBACK_NAME_MULTI.findall(text))
    pn += len(FALLBACK_NAME_SINGLE_LINE.findall(text))
    baseline['PERSON'] += pn

    # selected spans from redact
    out, spans = redact.redact(text, {}, source_name=p.name, return_spans=True)
    for s in spans:
        lab = s[2]
        if lab in labels:
            selected[lab] += 1

# print summary
print('Baseline candidates vs selected spans (phone baseline via phonenumbers):')
for l in labels:
    b = baseline[l]
    s = selected[l]
    pct = (s / b * 100) if b>0 else 0
    print(f"{l}: baseline={b}, selected={s}, selected_pct={pct:.1f}%")

print('\nLabels with <50% selection:')
for l in labels:
    b = baseline[l]
    s = selected[l]
    if b>0 and s/b < 0.5:
        print(f"  {l}: {s}/{b} = {s/b:.2f}")

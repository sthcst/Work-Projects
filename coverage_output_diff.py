import os, re
from pathlib import Path
import redact

# Run redact on each file and compare original vs redacted output to count removals
INDIR = Path('emails_folder/Spam/test_emails/generated_emails_bulk_long')
files = sorted(INDIR.glob('*.txt'))
# Optional sample limit to speed up runs for testing
SAMPLE = int(os.environ.get('SAMPLE', '0'))
if SAMPLE > 0:
    files = files[:SAMPLE]

labels = ['EMAIL','PHONE','SSN','DOB','ADDRESS','PERSON']
removed = {l:0 for l in labels}

def merge_spans(spans):
    """Merge a set/list of (start,end) spans into a list of non-overlapping spans."""
    if not spans:
        return []
    s = sorted(spans, key=lambda x: (x[0], x[1]))
    merged = []
    cur_start, cur_end = s[0]
    for a,b in s[1:]:
        if a <= cur_end:  # overlap or contiguous
            cur_end = max(cur_end, b)
        else:
            merged.append((cur_start, cur_end))
            cur_start, cur_end = a, b
    merged.append((cur_start, cur_end))
    return merged

def collect_spans(text):
    spans = {l:set() for l in labels}
    # EMAIL
    for m in redact.EMAIL.finditer(text):
        spans['EMAIL'].add((m.start(), m.end()))
    if hasattr(redact, 'OBFUSCATED_EMAIL') and redact.OBFUSCATED_EMAIL is not None:
        for m in redact.OBFUSCATED_EMAIL.finditer(text):
            spans['EMAIL'].add((m.start(), m.end()))
    # PHONE - always include regex-based matches (fallback), and also try phonenumbers for more robust parsing
    for m in redact.PHONE.finditer(text):
        spans['PHONE'].add((m.start(), m.end()))
    # Also include labeled phone pattern
    if hasattr(redact, 'PHONE_LABELED') and redact.PHONE_LABELED is not None:
        for m in redact.PHONE_LABELED.finditer(text):
            spans['PHONE'].add((m.start(), m.end()))
    try:
        import phonenumbers
        # use US as a sensible default region for parsing; phonenumbers will still find international numbers
        for match in phonenumbers.PhoneNumberMatcher(text, "US"):
            spans['PHONE'].add((match.start, match.end))
    except Exception:
        # if phonenumbers not installed or fails, we still have the regex matches
        pass
    # SSN strict + loose
    for m in redact.SSN_STRICT.finditer(text):
        spans['SSN'].add((m.start(), m.end()))
    # Respect STRICT_SSN: only include loose SSN when allowed or when nearby 'ssn' cue
    STRICT_SSN = os.environ.get('STRICT_SSN', '0') in ('1', 'true', 'True')
    for m in redact.SSN_LOOSE.finditer(text):
        if STRICT_SSN:
            ctx_start = max(0, m.start() - 30)
            ctx_end = min(len(text), m.end() + 10)
            context = text[ctx_start:ctx_end].lower()
            if 'ssn' in context or 'social security' in context or 'social-security' in context:
                spans['SSN'].add((m.start(), m.end()))
            else:
                # skip loose SSN when strict mode is enabled
                continue
        else:
            spans['SSN'].add((m.start(), m.end()))
    # DOB
    for m in redact.DOB.finditer(text):
        spans['DOB'].add((m.start(), m.end()))
    # ADDRESS variants
    for m in redact.ADDRESS.finditer(text):
        spans['ADDRESS'].add((m.start(), m.end()))
    for m in redact.ADDRESS_LOOSE.finditer(text):
        spans['ADDRESS'].add((m.start(), m.end()))
    for m in redact.ADDRESS_LABEL.finditer(text):
        spans['ADDRESS'].add((m.start(), m.end()))
    for m in redact.POSTAL_CODE.finditer(text):
        spans['ADDRESS'].add((m.start(), m.end()))
    for m in redact.APT_REGEX.finditer(text):
        spans['ADDRESS'].add((m.start(), m.end()))
    # PERSON - use spaCy NER spans if available (can be disabled via NO_SPACY env var)
    # PERSON collection: respect FORCE_NER_PERSON to prefer NER-only
    FORCE_NER_PERSON = os.environ.get('FORCE_NER_PERSON', '0') in ('1', 'true', 'True')
    # Prefer spaCy NER if available
    if not os.environ.get('NO_SPACY'):
        try:
            if redact.nlp is not None:
                doc = redact.nlp(text)
                for ent in doc.ents:
                    if ent.label_ == 'PERSON':
                        spans['PERSON'].add((ent.start_char, ent.end_char))
        except Exception:
            pass

    # If FORCE_NER_PERSON is set then do not add heuristic fallbacks
    if not FORCE_NER_PERSON:
        # fallback patterns
        for m in redact.FALLBACK_NAME_MULTI.finditer(text):
            spans['PERSON'].add((m.start(), m.end()))
        for m in redact.FALLBACK_NAME_SINGLE_LINE.finditer(text):
            spans['PERSON'].add((m.start(1), m.end(1)))
        # capitalized sequences and single capitalized words (only heuristic)
        cap_seq = re.compile(r"\b[A-Z][a-z]{1,}(?:\s+[A-Z][a-z]{1,}){0,2}\b")
        for m in cap_seq.finditer(text):
            spans['PERSON'].add((m.start(), m.end()))
        cap_single = re.compile(r"\b[A-Z][a-z]{2,}\b")
        for m in cap_single.finditer(text):
            spans['PERSON'].add((m.start(), m.end()))

    # merge spans per label to deduplicate overlapping matches
    merged = {l: merge_spans(spans[l]) for l in labels}
    return merged


for p in files:
    text = p.read_text(encoding='utf-8', errors='ignore')
    # collect before spans
    before = collect_spans(text)

    # run redact in aggressive delete mode
    os.environ['REDACT_DELETE'] = '1'
    os.environ['DELETE_LABELS'] = 'EMAIL,PHONE,SSN,DOB,ADDRESS,PERSON'
    os.environ['REDACT_SAFETY_SWEEP'] = '1'
    os.environ['REDACT_AGGRESSIVE'] = '1'
    out = redact.redact(text, {}, source_name=p.name)
    out_text = out[0] if isinstance(out, tuple) else out

    after = collect_spans(out_text)

    # compute removed spans per label as merged-before spans that do not overlap any merged-after span
    for l in labels:
        mb = before[l]
        ma = after[l]
        for bs, be in mb:
            # check if any after span overlaps this before span
            overlapped = False
            for as_, ae in ma:
                if not (be <= as_ or bs >= ae):
                    overlapped = True
                    break
            if not overlapped:
                removed[l] += 1

# Print summary once
print('Final deletions measured by unique-span diff:')
for l in labels:
    print(f"{l}: {removed[l]}")

# Export low-confidence audit candidates from redact (if any) for manual review
try:
    audit = getattr(redact, 'LOW_CONF_CANDIDATES', None)
    if audit:
        import csv
        audit_path = Path('low_confidence_audit.csv')
        with audit_path.open('w', encoding='utf-8', newline='') as fh:
            writer = csv.writer(fh)
            writer.writerow(['source_file','label','start','end','score','snippet','candidate_source'])
            for row in audit:
                # row expected: (source_file, label, start, end, score, snippet, source)
                try:
                    writer.writerow([row[0], row[1], int(row[2]), int(row[3]), float(row[4]), row[5], row[6]])
                except Exception:
                    # be robust to unexpected row shapes
                    writer.writerow([str(x) for x in row])
        print('Wrote low-confidence audit CSV to', str(audit_path))
    else:
        print('No low-confidence audit candidates to write.')
except Exception as e:
    print('Failed to write audit CSV:', e)

# If redact tracked low-confidence candidates, export them for auditing
try:
    audit = getattr(redact, 'LOW_CONF_CANDIDATES', None)
    if audit:
        import csv
        with open('low_confidence_audit.csv', 'w', newline='', encoding='utf-8') as csvf:
            w = csv.writer(csvf)
            w.writerow(['source_file', 'label', 'start', 'end', 'score', 'snippet', 'source'])
            for row in audit:
                # row is (source_file, label, start, end, score, snippet, source)
                w.writerow(row)
        print(f"Wrote low_confidence_audit.csv ({len(audit)} rows)")
except Exception:
    pass

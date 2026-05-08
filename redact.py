import os
import re
import sys
from typing import Optional, Dict, Tuple, List

try:
    import spacy
except ImportError:
    spacy = None
    sys.stderr.write(
        "Warning: spaCy is not installed. NER-based redaction will be skipped.\n"
        "Install spaCy with:\n"
        "  python3 -m pip install -U spacy\n"
        "Then download a model:\n"
        "  python -m spacy download en_core_web_sm\n"
        "Or for higher accuracy (larger, needs torch):\n"
        "  python -m pip install -U \"spacy[transformers]\" && python -m spacy download en_core_web_trf\n"
    )


def get_nlp():
    """Return a loaded spaCy pipeline or None if unavailable.

    Tries the transformer model first, then falls back to the small model.
    """
    if spacy is None:
        return None

    for model in ("en_core_web_trf", "en_core_web_sm"):
        try:
            return spacy.load(model)
        except OSError:
            # model not installed, try next
            continue

    sys.stderr.write(
        "Warning: No spaCy model found (en_core_web_trf or en_core_web_sm).\n"
        "Install a model with:\n"
        "  python -m spacy download en_core_web_sm\n"
    )
    return None


# Load NER model (may be None)
nlp = get_nlp()

# We'll attempt to use libpostal dynamically inside redact() if it's installed.
HAS_LIBPOSTAL = False

# Redaction mode and confidence threshold:
# - REDACT_MODE: 'strict' (default) applies threshold filtering, 'legacy' preserves prior behavior (no threshold)
# - REDACT_THRESHOLD: float between 0 and 1 (default 0.8)
REDACT_MODE = os.environ.get('REDACT_MODE', 'strict')
try:
    REDACT_THRESHOLD = float(os.environ.get('REDACT_THRESHOLD', '0.8'))
except Exception:
    REDACT_THRESHOLD = 0.8

# Per-label thresholds (sensible defaults). You can tune these or set REDACT_THRESHOLD as fallback.
LABEL_THRESHOLDS = {
    'SSN': float(os.environ.get('THRESH_SSN', '0.65')),
    'ADDRESS': float(os.environ.get('THRESH_ADDRESS', '0.60')),
    'PHONE': float(os.environ.get('THRESH_PHONE', '0.80')),
    'EMAIL': float(os.environ.get('THRESH_EMAIL', '0.60')),
    'DOB': float(os.environ.get('THRESH_DOB', '0.90')),
    'PERSON': float(os.environ.get('THRESH_PERSON', '0.60')),
}

# Paranoid line redact option: when True and REDACT_MODE=='paranoid', entire lines
# containing any selected PII span will be replaced. Set via env var REDACT_PARANOID_LINE=1
REDACT_PARANOID_LINE = os.environ.get('REDACT_PARANOID_LINE', '0') in ('1', 'true', 'True')

# Option to permanently delete detected PII instead of replacing with tokens.
# Set via env var REDACT_DELETE=1
REDACT_DELETE = os.environ.get('REDACT_DELETE', '0') in ('1', 'true', 'True')
# Aggressive mode: accept all candidate spans and delete all PII labels.
# Enabled by default. Set REDACT_AGGRESSIVE=0 to disable if needed.
REDACT_AGGRESSIVE = os.environ.get('REDACT_AGGRESSIVE', '1') in ('1', 'true', 'True')
def get_delete_labels():
    """Return a set of labels the user wants deleted (read from env each call).

    Environment variable: DELETE_LABELS=SSN,EMAIL
    """
    _dl = os.environ.get('DELETE_LABELS', '')
    if not _dl:
        return set()
    return {l.strip().upper() for l in _dl.split(',') if l.strip()}

# Labels that are deleted by default (unless explicitly overridden). You can
# change this by setting DELETE_LABELS or by altering this set in code.
DEFAULT_DELETE_ALWAYS = {'SSN', 'DOB', 'EMAIL', 'PHONE'}

# Optional conservative safety sweep: after normal redaction, run additional
# regexes to remove any remaining PII matches. Controlled via env var:
# REDACT_SAFETY_SWEEP=1
REDACT_SAFETY_SWEEP = os.environ.get('REDACT_SAFETY_SWEEP', '0') in ('1', 'true', 'True')

# Strictness toggles to minimize false positives
STRICT_SSN = os.environ.get('STRICT_SSN', '0') in ('1', 'true', 'True')
# When STRICT_PERSON=1 we prefer spaCy NER and require multi-token fallbacks or strong contextual cues
STRICT_PERSON = os.environ.get('STRICT_PERSON', '0') in ('1', 'true', 'True')
# Force PERSON detection to rely only on spaCy NER (fallbacks are audited, not auto-deleted)
FORCE_NER_PERSON = os.environ.get('FORCE_NER_PERSON', '0') in ('1', 'true', 'True')

# Optional name gazetteer file (one name per line). Set env NAME_GAZETTEER=/path/to/names.txt
NAME_GAZETTEER_PATH = os.environ.get('NAME_GAZETTEER', '')
NAME_GAZETTEER = set()
if NAME_GAZETTEER_PATH and os.path.exists(NAME_GAZETTEER_PATH):
    try:
        with open(NAME_GAZETTEER_PATH, 'r', encoding='utf-8', errors='ignore') as f:
            for ln in f:
                n = ln.strip()
                if n:
                    NAME_GAZETTEER.add(n.lower())
    except Exception:
        NAME_GAZETTEER = set()

# Container for low-confidence candidates (tuples: source_file, label, start, end, score, snippet, source)
LOW_CONF_CANDIDATES: List[Tuple[str, str, int, int, float, str, str]] = []

# === REGEX PATTERNS ===
EMAIL = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b')
# Common obfuscated email forms used in text: 'name (at) domain dot com' or 'name [at] domain[.]com'
OBFUSCATED_EMAIL = re.compile(r"\b[\w.+-]+\s*(?:\(|\[)?(?:at|@)(?:\)|\])?\s*[\w.-]+\s*(?:\(|\[)?(?:dot|\.)+(?:\)|\])?\s*[A-Za-z]{2,}\b", re.IGNORECASE)
# Broader phone regex to catch more international-ish variants (still heuristic)
# Require at least 7 digits to avoid matching short numeric/date-like sequences.
PHONE = re.compile(r"\b(?=(?:.*\d){7,})(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{1,4}\)?[\s.-]?)?\d{3,4}[\s.-]?\d{3,4}\b")
# US Social Security Number (SSN) patterns:
# - strict: 123-45-6789 or 123 45 6789 or 123456789 (dashed, space-separated, or no separator)
# - loose: 9 digits (only accepted when nearby 'ssn' label is present)
SSN_STRICT = re.compile(r"\b(?:\d{3}-\d{2}-\d{4}|\d{3} \d{2} \d{4}|\d{9})\b")
SSN_LOOSE = re.compile(r"\b\d{9}\b")
# Labeled-line SSN patterns like 'SSN: 123456789' or 'Social Security: 123456789'
SSN_LABEL_LINE = re.compile(r'(?im)^(?:\s*(?:ssn|social security|social-security)\s*[:\-]?\s*)(\d{9})\s*$')

# Common date-of-birth formats (require a 4-digit year to reduce false positives)
_MONTHS = r'(?:Jan|January|Feb|February|Mar|March|Apr|April|May|Jun|June|Jul|July|Aug|August|Sep|September|Oct|October|Nov|November|Dec|December)'
_NUM_MONTH_DAY = r'(?:0?[1-9]|1[0-2])[\/\-](?:0?[1-9]|[12][0-9]|3[01])[\/\-](?:19|20)\d{2}'
_NUM_DAY_MONTH = r'(?:0?[1-9]|[12][0-9]|3[01])[\/\-](?:0?[1-9]|1[0-2])[\/\-](?:19|20)\d{2}'
_ISO = r'(?:19|20)\d{2}[\/\-](?:0?[1-9]|1[0-2])[\/\-](?:0?[1-9]|[12][0-9]|3[01])'
_MONTH_NAME = rf'{_MONTHS}\.?' + r'\s+\d{1,2},?\s+(?:19|20)\d{2}'

# Ensure DOB matches are bounded by non-digit characters to avoid leaving trailing digits
DOB = re.compile(rf"(?<!\d)(?:{_NUM_MONTH_DAY}|{_NUM_DAY_MONTH}|{_ISO}|{_MONTH_NAME})(?!\d)", re.IGNORECASE)

GREETING = re.compile(r'\b(Hi|Hello|Dear)\s+([A-Z][a-z]+)\b')
SIGNOFF = re.compile(r'(Thanks|Best|Sincerely|Regards)[,\n\s]+([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)')

# Address patterns: include PO Box and common street type patterns.
# We require either an explicit PO Box or a numeric street number and a street type
ADDRESS = re.compile(
    r"\b(?:"
    r"(?:P\.?\s*O\.?\s*Box\s+\d{1,6})"  # PO Box 1234
    r"|"  # or
    r"(?:\d{1,5}\s+[A-Za-z0-9.\- ]{2,80}\s+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Court|Ct|Terrace|Ter|Place|Pl|Square|Sq|Highway|Hwy|Route|Rte|Way|Walk|Row)\b(?:,?\s*[A-Za-z .]{2,80},\s*[A-Z]{2,3})?)"
    r")",
    re.IGNORECASE,
)

# Address label capture: require a colon or be at the start of a line to avoid accidental matches
# Examples: 'Address: 3050 Oak Ave' or at line-start 'Address\n3050 Oak Ave'
ADDRESS_LABEL = re.compile(r'(?im)^(?:\s*(?:address|addr|location)\s*[:\-]\s*)([^\n]{5,200})')

# Apartment/unit expressions
APT_REGEX = re.compile(r'\b(?:Apt|Apartment|Unit|Suite|#)\s*\d+\b', re.IGNORECASE)

# Loose address pattern: number + capitalized street name (no explicit street type).
# Low-confidence; useful for auditing and later threshold tuning.
ADDRESS_LOOSE = re.compile(r"\b\d{1,5}\s+[A-Z][a-z0-9]+(?:\s+[A-Z][a-z0-9]+){0,4}\b")

# Generic postal code patterns (US, Canada-ish, simple international fallback)
POSTAL_CODE = re.compile(r"\b(?:\d{5}(?:-\d{4})?|[A-Z]\d[A-Z][ -]?\d[A-Z]\d)\b", re.IGNORECASE)

# Optional fallback (used carefully)
# Fallback: prefer multi-word capitalized sequences (likely full names)
FALLBACK_NAME_MULTI = re.compile(r"\b(?:[A-Z][a-z]{3,})(?:\s+[A-Z][a-z]{3,})+\b")
# Single capitalized words are only replaced when they appear alone on a line
FALLBACK_NAME_SINGLE_LINE = re.compile(r"(?m)^\s*([A-Z][a-z]{3,}(?:\s+[A-Z][a-z]{3,})?)\s*$")

SAFE_WORDS = {
    "Admissions", "University", "College", "Semester",
    "Fall", "Winter", "Spring", "Summer",
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
    "Hawaii", "BYUH"
}


# === NER NAME REDACTION ===
def redact_names_ner(text: str, stats: Optional[Dict[str, int]] = None) -> str:
    # If spaCy or the model isn't available, skip NER step
    if nlp is None:
        return text

    doc = nlp(text)
    spans = []

    for ent in doc.ents:
        if ent.label_ == "PERSON":
            spans.append((ent.start_char, ent.end_char))

    # Replace from end → start to avoid index shifting
    for start, end in reversed(spans):
        text = text[:start] + "[PERSON]" + text[end:]

    if stats is not None:
        stats["NER_PERSON_REPLACED"] = stats.get("NER_PERSON_REPLACED", 0) + len(spans)

    return text


# === MAIN REDACTION FUNCTION ===
def redact(text: str, stats: Optional[Dict[str, int]] = None, source_name: Optional[str] = None, return_spans: bool = False):
    """Perform redaction using scored candidate spans and an optional confidence threshold.

    Spans are tuples (start, end, label, source, score). In 'legacy' mode (REDACT_MODE='legacy')
    we preserve prior behavior (no score threshold). In 'strict' mode we only auto-redact spans
    with score >= REDACT_THRESHOLD.
    """
    spans: List[Tuple[int, int, str, str, float]] = []

    def add_regex_spans(pattern, label, source='regex', score=0.8):
        for m in pattern.finditer(text):
            spans.append((m.start(), m.end(), label, source, float(score)))

    def cleanup_after_deletion(s: str) -> str:
        # Conservative cleanup to remove empty punctuation and tidy separators
        # Remove empty bracket pairs
        s = re.sub(r"\(\s*\)", '', s)
        s = re.sub(r"\[\s*\]", '', s)
        s = re.sub(r"<\s*>", '', s)
        s = re.sub(r'"\s*"', '', s)
        s = re.sub(r"'\s*'", '', s)

        # Normalize repeated separators like "; ;" or ", ," -> single separator
        s = re.sub(r'([,;:])\s*(?:[,;:]\s*)+', r'\1 ', s)

        # Remove separators at start/end of line
        lines = []
        for ln in s.splitlines():
            ln = re.sub(r'^[\s\-\:\,;\.]+', '', ln)
            ln = re.sub(r'[\s\-\:\,;\.]+$', '', ln)
            # Collapse multiple spaces
            ln = re.sub(r' {2,}', ' ', ln)
            # Remove lines that are now essentially empty or too short
            if len(re.sub(r'[^A-Za-z0-9]', '', ln).strip()) < 2:
                continue
            lines.append(ln)

        s = '\n'.join(lines)

        # Remove isolated plus signs (leftover from phone deletions)
        s = re.sub(r'\s+\+\s+', ' ', s)
        # Remove lone plus at end/start of lines
        s = re.sub(r'\+\s*($|\n)', r"\1", s)
        s = re.sub(r'(^|\n)\s*\+', r"\1", s)

        # Remove unmatched parentheses or angle brackets left behind
        s = re.sub(r'\(\s*', '', s)
        s = re.sub(r'\s*\)', '', s)
        s = re.sub(r'<\s*', '', s)
        s = re.sub(r'\s*>', '', s)

        # Collapse multiple spaces again and trim lines
        s = re.sub(r' {2,}', ' ', s)
        s = '\n'.join([ln.strip() for ln in s.splitlines() if ln.strip()])

        # Collapse multiple blank lines to at most two
        s = re.sub(r'\n{3,}', '\n\n', s)
        return s

    # Structured PII spans with heuristic scores
    add_regex_spans(EMAIL, 'EMAIL', source='regex_email', score=0.98)
    # Obfuscated emails: increase base score so cue-based boosts can push them over threshold
    add_regex_spans(OBFUSCATED_EMAIL, 'EMAIL', source='regex_email_obf', score=0.70)
    # Prefer phonenumbers library when available for robust phone detection
    try:
        import phonenumbers
        phone_cues = {'phone', 'tel', 'telephone', 'call', 'mobile', 'cell', 'fax', 'contact'}
        for match in phonenumbers.PhoneNumberMatcher(text, None):
            try:
                pn = match.number
                s, e = match.start, match.end
                nsn = phonenumbers.national_significant_number(pn)
                if len(re.sub(r'\D', '', nsn)) < 7:
                    continue
                # skip if in code blocks or URLs
                line_start = text.rfind('\n', 0, s)
                if line_start == -1:
                    line_start = 0
                else:
                    line_start += 1
                line_end = text.find('\n', e)
                if line_end == -1:
                    line_end = len(text)
                line = text[line_start:line_end]
                if 'http://' in line or 'https://' in line or '://' in line or line.strip().startswith('```') or '`' in line:
                    continue
                ctx = text[max(0, s-40):s].lower()
                score = 0.9
                if any(cue in ctx for cue in phone_cues):
                    score = 0.98
                spans.append((s, e, 'PHONE', 'phonenumbers', float(score)))
            except Exception:
                continue
    except Exception:
        # fallback to regex-based detection
        phone_cues = {'phone', 'tel', 'telephone', 'call', 'mobile', 'cell', 'fax', 'contact'}
        for m in PHONE.finditer(text):
            s, e = m.start(), m.end()
            candidate = text[s:e]
            digits = re.sub(r'\D', '', candidate)
            if len(digits) < 7:
                continue
            if ':' in candidate and re.search(r'\d{1,2}:\d{2}', candidate):
                continue
            line_start = text.rfind('\n', 0, s)
            if line_start == -1:
                line_start = 0
            else:
                line_start += 1
            line_end = text.find('\n', e)
            if line_end == -1:
                line_end = len(text)
            line = text[line_start:line_end]
            if 'http://' in line or 'https://' in line or '://' in line or line.strip().startswith('```') or '`' in line:
                continue
            ctx = text[max(0, s-30):s].lower()
            score = 0.85
            if any(cue in ctx for cue in phone_cues):
                score = 0.95
            spans.append((s, e, 'PHONE', 'regex_phone', float(score)))
    add_regex_spans(SSN_STRICT, 'SSN', source='regex_ssn_strict', score=0.98)
    # Add loose 9-digit SSN matches only when a nearby 'ssn' cue exists (lower confidence)
    for m in SSN_LOOSE.finditer(text):
        # Use a wider context window to catch labeling like 'SSN: ...' or 'Social Security Number'
        ctx_start = max(0, m.start() - 100)
        ctx_end = min(len(text), m.end() + 100)
        context = text[ctx_start:ctx_end].lower()
        ssn_context_keywords = [
            'ssn', 'social security', 'social-security', 'tax id', 'taxid', 'ssn:', 'ssn is',
            'account number', 'account no', 'acct no', 'acct', 'member id', 'id number', 'id no', 'customer id'
        ]

        # Build a list of phone-like spans to avoid misclassifying parts of phone numbers as SSNs
        phone_spans = []
        try:
            import phonenumbers
            for pm in phonenumbers.PhoneNumberMatcher(text, None):
                phone_spans.append((pm.start, pm.end))
        except Exception:
            for pm in PHONE.finditer(text):
                phone_spans.append((pm.start(), pm.end()))
        # If this 9-digit sequence appears on a labeled line like 'SSN: 123456789', promote it.
        # Check the full line containing the match.
        line_start = text.rfind('\n', 0, m.start())
        if line_start == -1:
            line_start = 0
        else:
            line_start += 1
        line_end = text.find('\n', m.end())
        if line_end == -1:
            line_end = len(text)
        line_text = text[line_start:line_end]
        if SSN_LABEL_LINE.search(line_text):
            spans.append((m.start(), m.end(), 'SSN', 'regex_ssn_labeled_line', 0.98))
            continue

        # If this 9-digit sequence overlaps or is adjacent to a detected phone span, treat it as phone-like and skip
        overlapped_phone = False
        for ps,pe in phone_spans:
            # overlap or within 3 characters adjacency
            if not (m.end() + 3 < ps or m.start() - 3 > pe):
                overlapped_phone = True
                break
        # In aggressive mode, accept loose 9-digit SSN matches unconditionally (bypass phone-overlap check).
        if REDACT_AGGRESSIVE:
            spans.append((m.start(), m.end(), 'SSN', 'regex_ssn_loose_aggressive', 0.95))
        elif overlapped_phone:
            # mark as phone-overlap in audit so it's clear why it wasn't deleted
            snippet = text[max(0, m.start()-40):min(len(text), m.end()+40)].replace('\n',' ')
            LOW_CONF_CANDIDATES.append((source_name or '<unknown>', 'SSN', m.start(), m.end(), 0.2, snippet, 'regex_ssn_phone_overlap'))
            continue
        else:
            # If STRICT_SSN is enabled, only accept loose SSN when explicit 'ssn' label appears
            if STRICT_SSN:
                if any(k in context for k in ssn_context_keywords):
                    spans.append((m.start(), m.end(), 'SSN', 'regex_ssn_loose_strict', 0.98))
                else:
                    # Send to audit list instead of auto-accepting
                    snippet = text[max(0, m.start()-40):min(len(text), m.end()+40)].replace('\n',' ')
                    LOW_CONF_CANDIDATES.append((source_name or '<unknown>', 'SSN', m.start(), m.end(), 0.5, snippet, 'regex_ssn_loose_audit'))
            else:
                # previous behavior: accept when 'ssn' appears near the digits
                if any(k in context for k in ssn_context_keywords) or REDACT_AGGRESSIVE:
                    spans.append((m.start(), m.end(), 'SSN', 'regex_ssn_loose', 0.95))

    # Add DOB matches but skip ISO dates that are immediately followed by a time-of-day
    for m in DOB.finditer(text):
        # if this was an ISO-style date, check for immediate time-of-day after it
        span_txt = m.group(0)
        span_end = m.end()
        # look for time patterns like ' 12:00' or ' 12:00:00' immediately after
        if re.match(r"^(?:19|20)\d{2}[\/-]", span_txt):
            lookahead = text[span_end:span_end+10]
            if re.match(r"^\s*\d{1,2}:\d{2}(?::\d{2})?", lookahead):
                # lookahead looks like a timestamp; skip this DOB candidate
                continue
        spans.append((m.start(), m.end(), 'DOB', 'regex_dob', 0.95))
    add_regex_spans(ADDRESS, 'ADDRESS', source='regex_address', score=0.80)
    # Loose address candidates are added with a lower score so they can be tuned via LABEL_THRESHOLDS
    add_regex_spans(ADDRESS_LOOSE, 'ADDRESS', source='regex_address_loose', score=0.60)
    add_regex_spans(ADDRESS_LABEL, 'ADDRESS', source='regex_address_label', score=0.8)
    add_regex_spans(APT_REGEX, 'ADDRESS', source='regex_apt', score=0.8)

    # Promote loose address matches when accompanied by a nearby postal code or state token
    for m in ADDRESS_LOOSE.finditer(text):
        start, end = m.start(), m.end()
        lookahead = text[end:end+60]
        lookbehind = text[max(0, start-40):start]
        # if a postal code or comma-separated city,state appears nearby, promote
        if POSTAL_CODE.search(lookahead) or re.search(r'\b[A-Z]{2}\b', lookahead) or POSTAL_CODE.search(lookbehind):
            spans.append((start, end, 'ADDRESS', 'regex_address_loose_boost', 0.75))

    # NER spans (PERSON) and higher-confidence address parses via libpostal/matcher
    if nlp is not None:
        doc = nlp(text)
        for ent in doc.ents:
            if ent.label_ == 'PERSON':
                spans.append((ent.start_char, ent.end_char, 'PERSON', 'ner', 0.92))

        # Try libpostal first (high confidence international address parsing) if available
        try:
            from importlib import import_module
            postal = import_module('postal.parser')
            libpostal_parse = postal.parse_address
            try:
                parsed = libpostal_parse(text)
                # parsed is a list of (component, label) tuples; components nearby in the
                # source text should be merged into a single address span to avoid fragmentation.
                comps: List[Tuple[int, int, str, str]] = []
                for comp, label in parsed:
                    comp = comp.strip()
                    if len(comp) < 3:
                        continue
                    idx = text.find(comp)
                    if idx != -1:
                        comps.append((idx, idx + len(comp), comp, label))

                # Merge components that are close together (gap <= 12 chars)
                comps_sorted = sorted(comps, key=lambda x: x[0])
                merged = []
                merged_labels = []
                for c in comps_sorted:
                    if not merged:
                        merged.append([c[0], c[1]])
                        merged_labels.append({c[3]})
                        continue
                    prev = merged[-1]
                    prev_labels = merged_labels[-1]
                    # if current starts within small gap of prev end, merge
                    if c[0] <= prev[1] + 12:
                        prev[1] = max(prev[1], c[1])
                        prev_labels.add(c[3])
                    else:
                        merged.append([c[0], c[1]])
                        merged_labels.append({c[3]})

                # Accept merged spans only when they contain at least one useful component label
                # and some textual cue (a digit, a street-type word, or 'po box'). This helps
                # avoid libpostal mis-parsing ordinary sentences as addresses.
                useful_labels = {'house_number', 'road', 'po_box', 'postcode'}
                street_cue_re = re.compile(r'\b(?:street|st|ave|road|rd|blvd|lane|ln|drive|dr|court|ct|place|pl|box)\b', re.IGNORECASE)
                for (start_idx, end_idx), labels in zip(merged, merged_labels):
                    span_txt = text[start_idx:end_idx]
                    if len(span_txt) < 5:
                        continue
                    if not (labels & useful_labels):
                        # If no useful label, skip to avoid noisy false positives
                        continue
                    # Require a street-type cue, a PO Box, or a digit followed by a capitalized word
                    if not (street_cue_re.search(span_txt) or 'po box' in span_txt.lower() or re.search(r'\b\d{1,5}\s+[A-Z][a-z]', span_txt)):
                        continue
                    if end_idx - start_idx > 300:
                        # too long to be a valid single address
                        continue
                    spans.append((start_idx, end_idx, 'ADDRESS', 'libpostal', 0.97))
            except Exception:
                # libpostal parse failed for this text; ignore and continue
                pass
        except Exception:
            # postal library isn't available or import failed
            pass

        # spaCy Matcher for address-like patterns
        try:
            from spacy.matcher import Matcher

            matcher = Matcher(nlp.vocab)
            street_types = [
                'street', 'st', 'avenue', 'ave', 'road', 'rd', 'boulevard', 'blvd',
                'lane', 'ln', 'drive', 'dr', 'court', 'ct', 'terrace', 'ter', 'place', 'pl',
                'square', 'sq', 'highway', 'hwy', 'route', 'rte', 'way', 'walk', 'row'
            ]

            # More flexible patterns: allow nouns/adjectives/proper nouns as street name tokens
            pat1 = [
                {'LIKE_NUM': True},
                {'POS': {'IN': ['PROPN', 'NOUN', 'ADJ']}, 'OP': '+'},
                {'LOWER': {'IN': street_types}}
            ]
            pat2 = [
                {'POS': {'IN': ['PROPN', 'NOUN', 'ADJ']}, 'OP': '+'},
                {'LOWER': {'IN': street_types}}
            ]
            pat3 = [{'LOWER': 'po'}, {'LOWER': 'box'}, {'IS_DIGIT': True, 'OP': '+'}]
            pat4 = [{'LOWER': {'IN': ['apt', 'unit', 'suite', '#']}}, {'IS_ASCII': True, 'OP': '+'}]

            matcher.add('ADDRESS', [pat1, pat2, pat3, pat4])
            for match_id, start, end in matcher(doc):
                s = doc[start].idx
                last = doc[end - 1]
                e = last.idx + len(last.text)
                # Determine token length of the match
                token_len = end - start
                # Check for proximity/descriptive cues immediately before the match
                prev_token = doc[start - 1].text.lower() if start > 0 else ''
                proximity_cues = {'near', 'by', 'around', 'next', 'close', 'nearby', 'at'}
                # If the match is short (1-2 tokens) and preceded by a proximity cue,
                # it's more likely to be a descriptive phrase ("near River Lane") rather
                # than an explicit postal address; demote its score so thresholds can filter it.
                if token_len <= 2 and prev_token in proximity_cues:
                    match_score = 0.60
                else:
                    # default matcher score slightly boosted for address recall
                    match_score = 0.92
                spans.append((s, e, 'ADDRESS', 'matcher', float(match_score)))
        except Exception:
            pass

    # Fallback name heuristics (lower confidence)
    cues = [
        'name', 'from:', 'to:', 'subject', 'dear ', 'hello ', 'hi ', 'sincerely', 'regards', 'thanks',
        'email', 'phone', 'ssn', 'address', 'born', 'dob', 'date of birth', 'ssn:'
    ]

    # Strong promotion cues: if these appear near a fallback name match, promote to deletable
    PERSON_PROMOTE_CUES = [
        'name on record', 'name on file', 'name on record:', 'name on file:', 'name on record -', 'name on file -'
    ]

    # Only add fallback PERSON heuristics when STRICT_PERSON is not set (aggressive always overrides)
    if not STRICT_PERSON or REDACT_AGGRESSIVE:
        for m in FALLBACK_NAME_MULTI.finditer(text):
            word = m.group(0)
            toks = [t.strip() for t in re.split(r"\s+", word) if t.strip()]
            start, end = m.start(), m.end()
            ctx_start = max(0, start - 80)
            ctx_end = min(len(text), end + 80)
            context = text[ctx_start:ctx_end].lower()

            # In aggressive mode, bypass SAFE_WORDS and accept fallback multi-word names
            if REDACT_AGGRESSIVE:
                spans.append((start, end, 'PERSON', 'fallback_multi_aggressive', 0.95))
            else:
                # If any token in the matched phrase is a known safe word, skip it
                if any(t in SAFE_WORDS or t.title() in SAFE_WORDS for t in toks):
                    continue
                # If a strong promotion cue exists nearby, promote this fallback to deletable
                if any(pc in context for pc in PERSON_PROMOTE_CUES):
                    spans.append((start, end, 'PERSON', 'fallback_multi_promoted', 0.92))
                    continue
                if any(cue in context for cue in cues):
                    if FORCE_NER_PERSON:
                        # audit only
                        snippet = text[max(0, start-40):min(len(text), end+40)].replace('\n',' ')
                        LOW_CONF_CANDIDATES.append((source_name or '<unknown>', 'PERSON', start, end, 0.55, snippet, 'audit_fallback_multi'))
                    else:
                        spans.append((start, end, 'PERSON', 'fallback_multi', 0.55))

        for m in FALLBACK_NAME_SINGLE_LINE.finditer(text):
            word = m.group(1)
            toks = [t.strip() for t in re.split(r"\s+", word) if t.strip()]
            if REDACT_AGGRESSIVE:
                spans.append((m.start(1), m.end(1), 'PERSON', 'fallback_single_aggressive', 0.95))
            else:
                # If any token in the single-line match is a known safe word, skip
                if any(t in SAFE_WORDS or t.title() in SAFE_WORDS for t in toks):
                    continue
                # For single-line fallbacks, require at least 2 tokens and contextual cues to be confident
                ctx_start = max(0, m.start(1) - 80)
                ctx_end = min(len(text), m.end(1) + 80)
                context = text[ctx_start:ctx_end].lower()
                if len(toks) >= 2 and any(cue in context for cue in cues):
                    # Promote single-line fallback if strong promotion cue exists nearby
                    single_ctx = text[max(0, m.start(1)-80):min(len(text), m.end(1)+80)].lower()
                    if any(pc in single_ctx for pc in PERSON_PROMOTE_CUES):
                        spans.append((m.start(1), m.end(1), 'PERSON', 'fallback_single_promoted', 0.92))
                        continue
                    if FORCE_NER_PERSON:
                        snippet = text[max(0, m.start(1)-40):min(len(text), m.end(1)+40)].replace('\n',' ')
                        LOW_CONF_CANDIDATES.append((source_name or '<unknown>', 'PERSON', m.start(1), m.end(1), 0.6, snippet, 'audit_fallback_single'))
                    else:
                        spans.append((m.start(1), m.end(1), 'PERSON', 'fallback_single', 0.6))

    # Aggressive capitalized-sequence catch-all (only added when aggressive)
    if REDACT_AGGRESSIVE:
        CAP_SEQ = re.compile(r"\b[A-Z][a-z]{1,}(?:\s+[A-Z][a-z]{1,}){0,2}\b")
        for m in CAP_SEQ.finditer(text):
            s, e = m.start(), m.end()
            spans.append((s, e, 'PERSON', 'capseq_aggressive', 0.9))

    # Split ADDRESS spans around PERSON spans to preserve both
    person_spans = [s for s in spans if s[2] == 'PERSON']
    address_spans = [s for s in spans if s[2] == 'ADDRESS']
    email_spans = [s for s in spans if s[2] == 'EMAIL']

    # Remove PERSON spans that overlap EMAIL spans. This prevents spaCy from
    # blocking an EMAIL candidate when both tag the same tokens (e.g. obfuscated
    # emails where 'jane_doe' may be detected as PERSON). Prefer EMAIL when
    # there's overlap.
    filtered_person_spans2 = []
    for p in person_spans:
        p_start, p_end = p[0], p[1]
        overlaps_email = False
        for e in email_spans:
            e_start, e_end = e[0], e[1]
            if not (p_end <= e_start or p_start >= e_end):
                overlaps_email = True
                break
        if not overlaps_email:
            filtered_person_spans2.append(p)
    person_spans = filtered_person_spans2

    # Filter out PERSON spans that are likely address artifacts. spaCy sometimes
    # tags fragments like 'P.O. Box' as PERSON. If a PERSON span is entirely
    # contained within a high-confidence ADDRESS span (libpostal, matcher, or
    # the numeric regex_address), drop the PERSON span so the ADDRESS is kept.
    filtered_person_spans = []
    for p in person_spans:
        p_start, p_end = p[0], p[1]
        p_source = p[3] if len(p) >= 4 else 'ner'
        p_text = text[p_start:p_end].lower()
        contained_in_address = False
        for a in address_spans:
            a_start, a_end = a[0], a[1]
            a_source = a[3] if len(a) >= 4 else 'regex_address'
            if a_start <= p_start and a_end >= p_end:
                # If the address source is high-confidence, prefer ADDRESS
                if a_source in ('libpostal', 'matcher', 'regex_address'):
                    contained_in_address = True
                    break
                # Also prefer ADDRESS if the PERSON text clearly looks like an
                # address token (PO Box, box, p.o.)
                if re.search(r'\bpo\b|p\.o\.|\bbox\b', p_text, re.IGNORECASE):
                    contained_in_address = True
                    break
        if not contained_in_address:
            filtered_person_spans.append(p)
    person_spans = filtered_person_spans
    other_spans = [s for s in spans if s[2] not in ('PERSON', 'ADDRESS')]

    resolved_spans = list(other_spans)
    person_added = set()

    for a in address_spans:
        a_start, a_end = a[0], a[1]
        a_source = a[3] if len(a) >= 4 else 'regex_address'
        a_score = a[4] if len(a) >= 5 else 0.7
        overlapping = sorted([p for p in person_spans if not (p[1] <= a_start or p[0] >= a_end)], key=lambda x: x[0])
        cur = a_start
        for p in overlapping:
            p_start, p_end = p[0], p[1]
            p_source = p[3] if len(p) >= 4 else 'ner'
            p_score = p[4] if len(p) >= 5 else 0.9
            if p_start > cur:
                resolved_spans.append((cur, p_start, 'ADDRESS', a_source, a_score))
            resolved_spans.append((p_start, p_end, 'PERSON', p_source, p_score))
            person_added.add((p_start, p_end))
            cur = max(cur, p_end)
        if cur < a_end:
            resolved_spans.append((cur, a_end, 'ADDRESS', a_source, a_score))

    for p in person_spans:
        p_start, p_end = p[0], p[1]
        p_source = p[3] if len(p) >= 4 else 'ner'
        p_score = p[4] if len(p) >= 5 else 0.9
        if (p_start, p_end) not in person_added:
            resolved_spans.append((p_start, p_end, 'PERSON', p_source, p_score))

    # Resolve overlaps with priority and score
    priority = {
        'EMAIL': 100,
        'PHONE': 100,
        'SSN': 100,
        'DOB': 95,
        'ADDRESS': 90,
        'PERSON': 95,
    }

    # Normalize resolved spans to 5-tuples (start,end,label,source,score)
    normalized: List[Tuple[int, int, str, str, float]] = []
    for s in resolved_spans:
        if len(s) == 5:
            normalized.append(s)
        elif len(s) == 3:
            normalized.append((s[0], s[1], s[2], 'legacy', 0.7))

    # Pre-filter ADDRESS candidates that are just the literal word 'address' or
    # short phrases containing 'address' without digits or street cues. This
    # prevents false positives like "No address here..." being marked.
    street_cue_re = re.compile(r'\b(?:street|st|ave|road|rd|blvd|lane|ln|drive|dr|court|ct|place|pl|box)\b', re.IGNORECASE)
    filtered: List[Tuple[int, int, str, str, float]] = []
    for s in normalized:
        if s[2] == 'ADDRESS':
            span_txt = text[s[0]:s[1]]
            # If the span contains the literal word 'address' and lacks digits or street cues, skip it
            if re.search(r'\baddress\b', span_txt, re.IGNORECASE) and not (re.search(r'\d', span_txt) or street_cue_re.search(span_txt) or 'po box' in span_txt.lower()):
                continue
            # Also skip very short spans that are unlikely to be addresses
            if len(span_txt.strip()) < 4:
                continue
        filtered.append(s)

    spans_sorted = sorted(filtered, key=lambda s: (s[0], -(s[1] - s[0]), -priority.get(s[2], 0), -s[4]))

    selected: List[Tuple[int, int, str]] = []
    occupied = [False] * (len(text) + 1)

    for start, end, label, source, score in spans_sorted:
        if end <= start or start < 0 or end > len(text):
            continue
        # determine threshold for this label (paranoid mode overrides thresholds)
        if REDACT_MODE == 'paranoid' or REDACT_AGGRESSIVE:
            accept = True
        else:
            # special-case: accept single-line fallback PERSON spans even if score is low.
            if label == 'PERSON' and source == 'fallback_single':
                accept = True
            else:
                thresh = LABEL_THRESHOLDS.get(label, REDACT_THRESHOLD)
                if score < thresh:
                    # record low-confidence candidates for audit if reasonably close
                    try:
                        if score >= max(0.4, thresh - 0.25):
                            snippet = text[max(0, start-40):min(len(text), end+40)].replace('\n', ' ')
                            LOW_CONF_CANDIDATES.append((source_name or '<unknown>', label, start, end, score, snippet, source))
                    except Exception:
                        pass
                    accept = False
                else:
                    accept = True
        if not accept:
            continue
        if any(occupied[i] for i in range(start, end)):
            continue
        selected.append((start, end, label))
        for i in range(start, end):
            occupied[i] = True

    # Replace selected spans from end->start
    label_map = {
        'EMAIL': '[EMAIL]',
        'PHONE': '[PHONE]',
        'SSN': '[SSN]',
        'DOB': '[DOB]',
        'ADDRESS': '[ADDRESS]',
        'PERSON': '[PERSON]',
    }

    # If paranoid line redact is enabled, expand selected spans to entire lines
    if REDACT_MODE == 'paranoid' and REDACT_PARANOID_LINE:
        line_selected = []
        for start, end, label in selected:
            # expand to line boundaries
            line_start = text.rfind('\n', 0, start)
            if line_start == -1:
                line_start = 0
            else:
                line_start += 1
            line_end = text.find('\n', end)
            if line_end == -1:
                line_end = len(text)
            line_selected.append((line_start, line_end, label))
        selected = list({(s,e,l) for s,e,l in line_selected})

    # Merge nearby ADDRESS spans to avoid fragmentary multiple [ADDRESS] tokens for one logical address
    merged_selected: List[Tuple[int, int, str]] = []
    if selected:
        sel_sorted = sorted(selected, key=lambda s: s[0])
        cur_start, cur_end, cur_label = sel_sorted[0]
        for st, ed, lab in sel_sorted[1:]:
            if cur_label == 'ADDRESS' and lab == 'ADDRESS' and st <= cur_end + 12:
                # merge close ADDRESS spans
                cur_end = max(cur_end, ed)
            else:
                merged_selected.append((cur_start, cur_end, cur_label))
                cur_start, cur_end, cur_label = st, ed, lab
        merged_selected.append((cur_start, cur_end, cur_label))
    else:
        merged_selected = []

    # Before replacing, try to expand ADDRESS spans to include nearby postal codes or state/postal fragments
    expanded_selected: List[Tuple[int, int, str]] = []
    for start, end, label in merged_selected:
        if label == 'ADDRESS':
            # look ahead a short distance for postal code or state/postal fragments
            lookahead = text[end:end+60]
            m = POSTAL_CODE.search(lookahead)
            if m and m.start() <= 6:
                # extend to include punctuation and the postal code
                end = end + m.end()
            else:
                # try to include a trailing ", City, ST" pattern if present
                city_state = re.match(r"^\s*,?\s*[A-Za-z .]{2,50},\s*[A-Z]{2}\b", lookahead)
                if city_state:
                    end = end + city_state.end()
        expanded_selected.append((start, end, label))

    # Before replacing, compute replacement counts so stats work even when we delete
    replacement_counts = {}
    for _s, _e, _lab in expanded_selected:
        replacement_counts[_lab] = replacement_counts.get(_lab, 0) + 1

    # If stats dict provided, record counts now (works for delete or token modes)
    if stats is not None:
        stats_map = {
            'ADDRESS': 'ADDRESS_REPLACED',
            'PERSON': 'PERSON_REPLACED',
            'EMAIL': 'EMAIL_REPLACED',
            'PHONE': 'PHONE_REPLACED',
            'SSN': 'SSN_REPLACED',
            'DOB': 'DOB_REPLACED',
        }
        for lab, cnt in replacement_counts.items():
            key = stats_map.get(lab)
            if key:
                stats[key] = stats.get(key, 0) + cnt

    # Determine per-label delete set at runtime; default to DEFAULT_DELETE_ALWAYS when unset
    # If aggressive mode is enabled, delete all known PII labels.
    if REDACT_AGGRESSIVE:
        delete_labels = {'EMAIL', 'PHONE', 'SSN', 'DOB', 'ADDRESS', 'PERSON'}
    else:
        delete_labels = get_delete_labels() or set(DEFAULT_DELETE_ALWAYS)
    did_delete = False
    for start, end, label in sorted(expanded_selected, key=lambda s: s[0], reverse=True):
        if REDACT_DELETE or label in delete_labels:
            # remove the span entirely
            text = text[:start] + text[end:]
            did_delete = True
        else:
            repl = label_map.get(label, '[REDACTED]')
            text = text[:start] + repl + text[end:]

    # Greetings and signoffs
    text = GREETING.sub(lambda m: f"{m.group(1)} [PERSON]", text)

    def repl_signoff(m):
        replaced = m.group(0).replace(m.group(2), "[PERSON]")
        return replaced

    text = SIGNOFF.sub(repl_signoff, text)

    # Post-processing cleanup
    text = re.sub(r'\]\[', '] [', text)
    text = re.sub(r'(\[ADDRESS\])(?:\s+\[ADDRESS\])+', r'\1', text)
    text = re.sub(r'(\[PERSON\])(?:\s+\[PERSON\])+', r'\1', text)
    text = re.sub(r'(\[EMAIL\])(?:\s+\[EMAIL\])+', r'\1', text)
    text = re.sub(r'(\[PHONE\])(?:\s+\[PHONE\])+', r'\1', text)
    text = re.sub(r'(\[SSN\])(?:\s+\[SSN\])+', r'\1', text)
    text = re.sub(r'(\[DOB\])(?:\s+\[DOB\])+', r'\1', text)

    # If we deleted spans, collapse excessive whitespace and remove empty lines
    if did_delete or REDACT_DELETE:
        # collapse multiple spaces/tabs
        text = re.sub(r'[ \t]{2,}', ' ', text)
        # strip trailing spaces from each line
        text = '\n'.join([ln.rstrip() for ln in text.splitlines()])
        # collapse 3+ newlines to two (preserve paragraph breaks)
        text = re.sub(r'\n{3,}', '\n\n', text)

    # Run conservative cleanup if deletions occurred
    if did_delete:
        try:
            text = cleanup_after_deletion(text)
        except Exception:
            pass

    # Optional safety sweep: remove remaining matches by regex to maximize deletion
    if REDACT_SAFETY_SWEEP:
        text_before = text
        # remove explicit emails and obfuscated ones
        try:
            text = EMAIL.sub('', text)
        except Exception:
            pass
        if OBFUSCATED_EMAIL is not None:
            try:
                text = OBFUSCATED_EMAIL.sub('', text)
            except Exception:
                pass
        # phones
        try:
            text = PHONE.sub('', text)
        except Exception:
            pass
        # SSN strict
        try:
            text = SSN_STRICT.sub('', text)
        except Exception:
            pass
        # DOB sweep (skip ISO date followed by time)
        def _dob_sweep(m):
            span_txt = m.group(0)
            if re.match(r"^(?:19|20)\d{2}[\/-]", span_txt):
                lookahead = text[m.end():m.end()+10]
                if re.match(r"^\s*\d{1,2}:\d{2}(?::\d{2})?", lookahead):
                    return m.group(0)
            return ''
        try:
            text = DOB.sub(_dob_sweep, text)
        except Exception:
            pass
        # ADDRESS strict
        try:
            text = ADDRESS.sub('', text)
        except Exception:
            pass

        # update stats with crude delta of token appearances
        if stats is not None:
            for lab, token in (('ADDRESS','[ADDRESS]'), ('PERSON','[PERSON]'), ('EMAIL','[EMAIL]'), ('PHONE','[PHONE]'), ('SSN','[SSN]'), ('DOB','[DOB]')):
                delta = text_before.count(token) - text.count(token)
                if delta > 0:
                    stats[lab + '_REPLACED'] = stats.get(lab + '_REPLACED', 0) + delta

    # Aggressive post-pass: if requested, remove any remaining address-like regex matches
    if REDACT_AGGRESSIVE:
        text_before = text
        try:
            # remove loose address patterns, labels, apartment/unit mentions, and postal codes
            new_text, n_loose = ADDRESS_LOOSE.subn('', text)
            new_text, n_label = ADDRESS_LABEL.subn('', new_text)
            new_text, n_apt = APT_REGEX.subn('', new_text)
            new_text, n_postal = POSTAL_CODE.subn('', new_text)
            text = new_text
        except Exception:
            n_loose = n_label = n_apt = n_postal = 0
        # update stats for any crude deletions performed
        if stats is not None:
            total_removed = int(n_loose + n_label + n_apt + n_postal)
            if total_removed > 0:
                stats['ADDRESS_REPLACED'] = stats.get('ADDRESS_REPLACED', 0) + total_removed
        # Aggressive person removals: strip multi-word fallback names and capitalized sequences
        try:
            # remove fallback multi-name patterns
            new_text, n_fm = FALLBACK_NAME_MULTI.subn('', text)
            # remove single-line fallback names
            new_text, n_fs = FALLBACK_NAME_SINGLE_LINE.subn('', new_text)
            # remove our aggressive capitalized sequences if present
            cap_seq = re.compile(r"\b[A-Z][a-z]{1,}(?:\s+[A-Z][a-z]{1,}){0,2}\b")
            new_text, n_cap = cap_seq.subn('', new_text)
            text = new_text
        except Exception:
            n_fm = n_fs = n_cap = 0
        if stats is not None:
            person_removed = int(n_fm + n_fs + n_cap)
            if person_removed > 0:
                stats['PERSON_REPLACED'] = stats.get('PERSON_REPLACED', 0) + person_removed
        # Aggressive SSN removals: remove loose 9-digit patterns unconditionally
        try:
            new_text, n_ssn_loose = SSN_LOOSE.subn('', text)
            text = new_text
        except Exception:
            n_ssn_loose = 0
        if stats is not None and n_ssn_loose > 0:
            stats['SSN_REPLACED'] = stats.get('SSN_REPLACED', 0) + int(n_ssn_loose)
        # Aggressive person single-word removal (very broad) when requested
        try:
            cap_single = re.compile(r"\b[A-Z][a-z]{2,}\b")
            new_text, n_cap_single = cap_single.subn('', text)
            text = new_text
        except Exception:
            n_cap_single = 0
        if stats is not None and n_cap_single > 0:
            stats['PERSON_REPLACED'] = stats.get('PERSON_REPLACED', 0) + int(n_cap_single)

    if return_spans:
        # return the redacted text and the list of expanded_selected spans for auditing
        return text, expanded_selected
    return text


# === FILE PROCESSOR ===
def process_file(input_path, output_path):
    # Maintain aggregated stats for this file
    stats: Dict[str, int] = {}

    with open(input_path, "r", encoding="utf-8", errors="ignore") as infile, \
         open(output_path, "w", encoding="utf-8") as outfile:

        buffer = []

        for line in infile:
            # Thunderbird email boundary
            if line.startswith("From "):
                if buffer:
                    email_text = "".join(buffer)
                    redacted = redact(email_text, stats, source_name=input_path)
                    if isinstance(redacted, tuple):
                        redacted_text, _spans = redacted
                    else:
                        redacted_text = redacted

                    outfile.write("\n--- EMAIL START ---\n")
                    outfile.write(redacted_text)
                    outfile.write("\n--- EMAIL END ---\n\n")

                    buffer = []

            buffer.append(line)

        # Process last email
        if buffer:
            email_text = "".join(buffer)
            redacted = redact(email_text, stats, source_name=input_path)
            if isinstance(redacted, tuple):
                redacted_text, _spans = redacted
            else:
                redacted_text = redacted

            outfile.write("\n--- EMAIL START ---\n")
            outfile.write(redacted_text)
            outfile.write("\n--- EMAIL END ---\n")

        # Append a small stats summary to the output file
        outfile.write("\n--- REDACTION SUMMARY ---\n")
        for k in sorted(stats.keys()):
            outfile.write(f"{k}: {stats[k]}\n")


# === RUN SCRIPT ===
import os

def process_folder(input_folder, output_file):
    # Aggregate stats across all files
    overall_stats: Dict[str, int] = {}

    with open(output_file, "w", encoding="utf-8") as outfile:

        for filename in os.listdir(input_folder):
            if not filename.endswith(".txt"):
                continue

            file_path = os.path.join(input_folder, filename)

            print(f"Processing: {filename}")

            with open(file_path, "r", encoding="utf-8", errors="ignore") as infile:
                buffer = []

                for line in infile:
                    if line.startswith("From "):
                        if buffer:
                            email_text = "".join(buffer)
                            redacted = redact(email_text, overall_stats, source_name=filename)
                            if isinstance(redacted, tuple):
                                redacted_text, _spans = redacted
                            else:
                                redacted_text = redacted

                            outfile.write("\n--- EMAIL START ---\n")
                            outfile.write(f"SOURCE: {filename}\n")
                            outfile.write(redacted_text)
                            outfile.write("\n--- EMAIL END ---\n\n")

                            buffer = []

                    buffer.append(line)

                # last email in file
                if buffer:
                    email_text = "".join(buffer)
                    redacted = redact(email_text, overall_stats, source_name=filename)
                    if isinstance(redacted, tuple):
                        redacted_text, _spans = redacted
                    else:
                        redacted_text = redacted

                    outfile.write("\n--- EMAIL START ---\n")
                    outfile.write(f"SOURCE: {filename}\n")
                    outfile.write(redacted_text)
                    outfile.write("\n--- EMAIL END ---\n\n")

    # After processing all files, append an overall stats summary
    with open(output_file, "a", encoding="utf-8") as outfile:
        outfile.write("\n=== AGGREGATED REDACTION STATS ===\n")
        if overall_stats:
            for k in sorted(overall_stats.keys()):
                outfile.write(f"{k}: {overall_stats[k]}\n")
        else:
            outfile.write("No redaction stats were collected.\n")


# === RUN SCRIPT ===
if __name__ == "__main__":
    input_folder = "emails_folder"   # folder with your .txt files
    output_file = "redacted_output.txt"

    print("Starting redaction on folder...")
    process_folder(input_folder, output_file)
    print("Done. Output saved to:", output_file)
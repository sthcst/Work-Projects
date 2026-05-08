import os
# request per-label delete via env
os.environ['DELETE_LABELS'] = 'SSN,DOB'

from redact import redact

cases = [
    ("SSN: 123-45-6789 in text", True),
    ("My ssn is 123456789", True),
    ("DOB: January 12, 1990 is my birthdate", True),
    ("Born on 1990-01-12", True),
    ("This is not a date 202312", False),
]

for text, expect_deleted in cases:
    out = redact(text)
    deleted = text != out and ('[SSN]' not in out and '[DOB]' not in out)
    result = 'PASS' if deleted == expect_deleted else 'FAIL'
    print(f"{result}: in='{text}' -> out='{out}' (deleted? {deleted})")

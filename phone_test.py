import os
# request PHONE deletion via DELETE_LABELS in this test
os.environ['DELETE_LABELS'] = 'PHONE'

from redact import redact

cases = [
    ("Call me at +1-808-555-1212", True),
    ("My number: (808) 555-1212", True),
    ("Timestamp: 2023-05-04 12:34:56", False),
    ("Short number 123-45 should not match", False),
    ("Code: `phone = '555-1212'`", False),
]

for text, expect_deleted in cases:
    out = redact(text)
    deleted = text != out and ('[PHONE]' not in out)
    result = 'PASS' if deleted == expect_deleted else 'FAIL'
    print(f"{result}: in='{text}' -> out='{out}' (deleted? {deleted})")

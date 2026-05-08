import os
# make EMAIL and PHONE deleted by default via DELETE_LABELS in this test
os.environ['DELETE_LABELS'] = 'EMAIL,PHONE'

from redact import redact

cases = [
    ("Contact me at john.doe@example.com", True),
    ("Email: jane_doe (at) example dot com", True),
    ("Call +1-808-555-1212 for info", True),
    ("Short number 12345 should not be a phone", False),
    ("Code sample: 2023-12-12 12:00:00", False),
]

for text, expect_deleted in cases:
    out = redact(text)
    deleted = text != out and ('[EMAIL]' not in out and '[PHONE]' not in out)
    result = 'PASS' if deleted == expect_deleted else 'FAIL'
    print(f"{result}: in='{text}' -> out='{out}' (deleted? {deleted})")

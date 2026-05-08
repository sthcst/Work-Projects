from redact import redact

cases = [
    ("John Doe sent the report.", True),
    ("Professor Smith lectured.", True),
    ("Dear Emily, thanks for your note.", True),
    ("Contact: A. B. Clark", True),
    ("Admissions Office", False),
    ("BYUH campus is large", False),
    ("Sincerely, Michael", True),
    ("Alice\n", True),
]

for text, expect_person in cases:
    out = redact(text)
    found = '[PERSON]' in out
    result = 'PASS' if found == expect_person else 'FAIL'
    print(f"{result}: in='{text.strip()}' -> out='{out.strip()}' (expected person? {expect_person})")

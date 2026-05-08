from redact import redact

cases = [
    ("3050 Oak Ave, Honolulu, HI 96701", True),
    ("P.O. Box 1234, Somecity, CA 90210", True),
    ("123 Fake St Apt 4B", True),
    ("Meet me at the old mill near River Lane", False),
    ("Call me at +1-808-555-1212", False),
    ("No address here, just a sentence about nothing.", False),
    ("My address is: 12 Downing St", True),
    ("Professor Smith lectured on January 18th", False),
]

for text, expect_address in cases:
    out = redact(text)
    found = '[ADDRESS]' in out
    result = 'PASS' if found == expect_address else 'FAIL'
    print(f"{result}: in='{text}' -> out='{out}' (expected address? {expect_address})")

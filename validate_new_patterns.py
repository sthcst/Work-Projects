#!/usr/bin/env python3
"""Validate that new patterns (DOB 2-digit year, rural routes, initials, name context, city-state) are detected."""

import sys
import os
sys.path.insert(0, '/Users/acostasv/Documents/Work Projects')

# Set aggressive mode
os.environ['REDACT_AGGRESSIVE'] = '1'
os.environ['REDACT_DELETE'] = '1'

import redact

# Test samples for new patterns
test_cases = {
    "DOB 2-digit year (MM/DD/YY)": [
        "Patient DOB: 01/15/90",
        "Birth date 12/25/85",
        "Date: 05/10/92"
    ],
    "DOB month name no comma": [
        "Born January 15 1990",
        "DOB: February 20 1985",
        "Birthday March 10 1992"
    ],
    "Rural routes": [
        "Address: R.R. 5 Box 123, Springfield, IL",
        "Located at RR 5 Box 456",
        "Rural Route 3, County Road 5"
    ],
    "City + State": [
        "Springfield, IL",
        "New York, NY",
        "Los Angeles, CA"
    ],
    "Initials (Person)": [
        "Contact: J. Smith",
        "Signed by John S.",
        "From J.D. to team"
    ],
    "Name context": [
        "Name: John Smith",
        "Called by Sarah",
        "From Mary Johnson",
        "Mr. Robert called",
        "Dr. Emily confirmed"
    ]
}

print("=" * 80)
print("NEW PATTERN VALIDATION TEST")
print("=" * 80)

for category, samples in test_cases.items():
    print(f"\n📋 {category}")
    print("-" * 80)
    
    all_detected = True
    for sample_text in samples:
        redacted = redact.redact(sample_text, {}, source_name="test")
        redacted_text = redacted[0] if isinstance(redacted, tuple) else redacted
        
        # Check if something was deleted (i.e., redaction occurred)
        if redacted_text != sample_text:
            status = "✅ DETECTED"
        else:
            status = "❌ NOT DETECTED"
            all_detected = False
        
        print(f"  {status}")
        print(f"    Original:  {sample_text[:70]}")
        print(f"    Redacted:  {redacted_text[:70]}")
        print()
    
    if all_detected:
        print(f"✅ {category}: All samples detected and redacted")
    else:
        print(f"⚠️  {category}: Some samples not detected")

print("\n" + "=" * 80)
print("VALIDATION COMPLETE")
print("=" * 80)

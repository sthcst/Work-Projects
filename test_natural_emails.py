#!/usr/bin/env python3
"""Test redaction coverage on natural language email corpus."""

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, '/Users/acostasv/Documents/Work Projects')
import redact

# Enable aggressive redaction
os.environ['REDACT_AGGRESSIVE'] = '1'
os.environ['REDACT_DELETE'] = '1'
os.environ['DELETE_LABELS'] = 'EMAIL,PHONE,SSN,DOB,ADDRESS,PERSON'
os.environ['REDACT_SAFETY_SWEEP'] = '1'
os.environ['NO_SPACY'] = '0'
os.environ['FORCE_NER_PERSON'] = '0'

# Reload redact to pick up env changes
import importlib
importlib.reload(redact)

# Test corpus
CORPUS_DIR = Path('test_emails_naturallanguage')
test_files = sorted(CORPUS_DIR.glob('email_*.txt'))

print(f"Testing {len(test_files)} natural language email files")
print("=" * 80)

# PII detection patterns
email_pattern = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b')
phone_pattern = redact.PHONE
phone_labeled = redact.PHONE_LABELED if hasattr(redact, 'PHONE_LABELED') else None
ssn_strict = re.compile(r"\b(?:\d{3}-\d{2}-\d{4}|\d{3} \d{2} \d{4}|\d{9})\b")
dob_pattern = re.compile(r'\b(?:0?[1-9]|1[0-2])[/\-](?:0?[1-9]|[12][0-9]|3[01])[/\-](?:19|20)\d{2}\b')
capitalized_seq = re.compile(r'\b[A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})+\b')

# Summary stats
total_before = {'EMAIL': 0, 'PHONE': 0, 'SSN': 0, 'DOB': 0, 'PERSON': 0}
total_after = {'EMAIL': 0, 'PHONE': 0, 'SSN': 0, 'DOB': 0, 'PERSON': 0}
deleted = {'EMAIL': 0, 'PHONE': 0, 'SSN': 0, 'DOB': 0, 'PERSON': 0}
files_with_misses = []

for test_file in test_files:
    orig_text = test_file.read_text(encoding='utf-8', errors='ignore')
    
    # Count before
    before = {
        'EMAIL': len(email_pattern.findall(orig_text)),
        'PHONE': len(phone_pattern.findall(orig_text)) + (len(phone_labeled.findall(orig_text)) if phone_labeled else 0),
        'SSN': len(ssn_strict.findall(orig_text)),
        'DOB': len(dob_pattern.findall(orig_text)),
        'PERSON': len(capitalized_seq.findall(orig_text)),
    }
    
    # Redact
    redacted = redact.redact(orig_text, {}, source_name=test_file.name)
    redacted_text = redacted[0] if isinstance(redacted, tuple) else redacted
    
    # Count after
    after = {
        'EMAIL': len(email_pattern.findall(redacted_text)),
        'PHONE': len(phone_pattern.findall(redacted_text)) + (len(phone_labeled.findall(redacted_text)) if phone_labeled else 0),
        'SSN': len(ssn_strict.findall(redacted_text)),
        'DOB': len(dob_pattern.findall(redacted_text)),
        'PERSON': len(capitalized_seq.findall(redacted_text)),
    }
    
    # Track misses
    misses = {k: after[k] for k in after if after[k] > 0}
    if misses:
        files_with_misses.append((test_file.name, misses))
    
    # Accumulate
    for label in total_before:
        total_before[label] += before[label]
        total_after[label] += after[label]
        deleted[label] += before[label] - after[label]

print("\n=== COVERAGE BY LABEL ===")
for label in ['EMAIL', 'PHONE', 'SSN', 'DOB', 'PERSON']:
    total = total_before[label]
    removed = deleted[label]
    remaining = total_after[label]
    coverage = (removed / total * 100) if total > 0 else 0.0
    status = "✅" if remaining == 0 else "⚠️"
    print(f"{status} {label:8} — Total: {total:4}, Deleted: {removed:4}, Remaining: {remaining:4} ({coverage:5.1f}% coverage)")

print(f"\n=== SUMMARY ===")
total_pii = sum(total_before.values())
total_deleted = sum(deleted.values())
total_remaining = sum(total_after.values())
overall_coverage = (total_deleted / total_pii * 100) if total_pii > 0 else 0.0

print(f"Total PII found: {total_pii}")
print(f"Total deleted: {total_deleted}")
print(f"Total remaining: {total_remaining}")
print(f"Overall coverage: {overall_coverage:.1f}%")

if total_remaining == 0:
    print("\n✅ 100% COVERAGE ACHIEVED on natural language emails!")
else:
    print(f"\n⚠️ {total_remaining} PII items still remaining")
    if files_with_misses:
        print("\nFiles with missed PII:")
        for fname, misses in files_with_misses[:5]:
            print(f"  {fname}: {misses}")
        if len(files_with_misses) > 5:
            print(f"  ... and {len(files_with_misses) - 5} more")

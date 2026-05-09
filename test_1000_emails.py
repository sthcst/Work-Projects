#!/usr/bin/env python3
"""Test redaction coverage on 100000-email corpus."""

import os
import re
import sys
from pathlib import Path
from collections import defaultdict
import time

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
CORPUS_DIR = Path('test_emails_100000')
test_files = sorted(CORPUS_DIR.glob('email_*.txt'))

print(f"Testing {len(test_files)} emails from comprehensive corpus")
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
files_processed = 0
errors = []

start_time = time.time()
print("Processing emails...")
for i, test_file in enumerate(test_files, 1):
    if i % 5000 == 0:
        elapsed = time.time() - start_time
        rate = i / elapsed
        remaining = (len(test_files) - i) / rate
        print(f"  Processed {i:,}/{len(test_files):,}... ({rate:.0f} files/sec, ~{remaining:.0f}s remaining)")
    
    try:
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
            files_with_misses.append((test_file.name, misses, before))
        
        # Accumulate
        for label in total_before:
            total_before[label] += before[label]
            total_after[label] += after[label]
            deleted[label] += before[label] - after[label]
        
        files_processed += 1
    except Exception as e:
        errors.append((test_file.name, str(e)))

elapsed_time = time.time() - start_time

print(f"\nProcessed {files_processed:,}/{len(test_files):,} files in {elapsed_time:.1f} seconds")
if errors:
    print(f"Errors in {len(errors)} files (skipped)")

print("\n" + "=" * 80)
print("=== COVERAGE BY LABEL ===")
for label in ['EMAIL', 'PHONE', 'SSN', 'DOB', 'PERSON']:
    total = total_before[label]
    removed = deleted[label]
    remaining = total_after[label]
    coverage = (removed / total * 100) if total > 0 else 0.0
    status = "✅" if remaining == 0 else "⚠️"
    print(f"{status} {label:8} — Total: {total:7}, Deleted: {total:7}, Remaining: {remaining:7} ({coverage:5.1f}% coverage)")

print(f"\n=== SUMMARY ===")
total_pii = sum(total_before.values())
total_deleted = sum(deleted.values())
total_remaining = sum(total_after.values())
overall_coverage = (total_deleted / total_pii * 100) if total_pii > 0 else 0.0

print(f"Total PII found: {total_pii:,}")
print(f"Total deleted: {total_deleted:,}")
print(f"Total remaining: {total_remaining:,}")
print(f"Overall coverage: {overall_coverage:.1f}%")
print(f"Emails processed: {files_processed:,}")
print(f"Processing time: {elapsed_time:.1f} seconds ({elapsed_time/files_processed*1000:.1f}ms per email)")
print(f"Throughput: {files_processed/elapsed_time:.0f} emails/sec")

if total_remaining == 0:
    print("\n✅ 100% COVERAGE ACHIEVED on 100000-email corpus!")
else:
    print(f"\n⚠️ {total_remaining} PII items remaining across {len(files_with_misses)} files")
    print("\nTop 10 files with most misses:")
    sorted_misses = sorted(files_with_misses, key=lambda x: sum(x[1].values()), reverse=True)
    for fname, misses, before in sorted_misses[:10]:
        total_miss = sum(misses.values())
        print(f"  {fname}: {total_miss} remaining — {misses}")

# Export detailed report
report_file = Path('coverage_100000_emails.txt')
with open(report_file, 'w') as f:
    f.write("=" * 80 + "\n")
    f.write("100000-EMAIL CORPUS COVERAGE REPORT\n")
    f.write("=" * 80 + "\n\n")
    
    f.write(f"Emails processed: {files_processed:,}\n")
    f.write(f"Processing time: {elapsed_time:.1f} seconds\n")
    f.write(f"Throughput: {files_processed/elapsed_time:.0f} emails/sec\n")
    f.write(f"Total PII found: {total_pii:,}\n")
    f.write(f"Total deleted: {total_deleted:,}\n")
    f.write(f"Total remaining: {total_remaining:,}\n")
    f.write(f"Overall coverage: {overall_coverage:.1f}%\n\n")
    
    f.write("COVERAGE BY LABEL:\n")
    f.write("-" * 80 + "\n")
    for label in ['EMAIL', 'PHONE', 'SSN', 'DOB', 'PERSON']:
        total = total_before[label]
        removed = deleted[label]
        remaining = total_after[label]
        coverage = (removed / total * 100) if total > 0 else 0.0
        f.write(f"{label:8} — Total: {total:7}, Deleted: {removed:7}, Remaining: {remaining:7} ({coverage:5.1f}%)\n")
    
    if total_remaining > 0:
        f.write("\n\nFILES WITH MISSED PII:\n")
        f.write("-" * 80 + "\n")
        sorted_misses = sorted(files_with_misses, key=lambda x: sum(x[1].values()), reverse=True)
        for fname, misses, before in sorted_misses[:50]:
            f.write(f"\n{fname}:\n")
            for label, count in sorted(misses.items(), key=lambda x: -x[1]):
                f.write(f"  {label}: {count} remaining (out of {before[label]} found)\n")

print(f"\n📊 Detailed report saved to {report_file}")

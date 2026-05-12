#!/usr/bin/env python3
"""Quick test of multiprocessing redaction on 10K emails."""

import sys
import os
import shutil
sys.path.insert(0, '/Users/acostasv/Documents/Work Projects')

# Set aggressive mode
os.environ['REDACT_AGGRESSIVE'] = '1'
os.environ['REDACT_DELETE'] = '1'

import redact

# Test with different worker counts
test_cases = [
    ("Single-core", 1),
    ("2 workers", 2),
    ("4 workers", 4),
    ("6 workers", 6),
]

print("\n" + "="*80)
print("MULTIPROCESSING BENCHMARK - 10K EMAILS")
print("="*80 + "\n")

for label, num_workers in test_cases:
    output_file = f"redacted_output_{num_workers}w.txt"
    
    print(f"Testing: {label}")
    print(f"  Input: test_emails_10000/")
    print(f"  Workers: {num_workers}")
    
    redact.process_folder_multiprocess(
        "test_emails_10000",
        output_file,
        num_workers=num_workers
    )
    
    # Show file size
    size_mb = os.path.getsize(output_file) / (1024 * 1024)
    print(f"  Output size: {size_mb:.1f} MB")
    print()

print("="*80)
print("Benchmark complete! Check redacted_output_*w.txt files.")
print("="*80)

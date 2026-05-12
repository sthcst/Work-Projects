#!/usr/bin/env python3
"""Test multiprocessing on 10,000 emails."""
import sys
import os

# Set environment variables
os.environ['REDACT_AGGRESSIVE'] = '1'
os.environ['REDACT_DELETE'] = '1'

# Add workspace to path
sys.path.insert(0, '/Users/acostasv/Documents/Work Projects')

import redact

if __name__ == '__main__':
    print("Starting multiprocessing test on 10,000 emails with 6 workers...")
    print("-" * 60)
    redact.process_folder_multiprocess(
        "test_emails_10000", 
        "redacted_output_multiprocess_10k.txt", 
        num_workers=6
    )
    print("-" * 60)
    print("Test completed!")

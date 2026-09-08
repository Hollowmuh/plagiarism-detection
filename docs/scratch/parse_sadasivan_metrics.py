import re

with open(r'C:\Users\olomu\.gemini\antigravity-ide\brain\6235f750-ffe1-4edc-91cb-04c08b593da4\.system_generated\steps\369\content.md', 'r', encoding='utf-8', errors='ignore') as f:
    text = f.read()

lines = text.splitlines()

# Search for RoBERTa, detectors, AUC, tables
for i, l in enumerate(lines):
    if any(k in l.lower() for k in ['table 1', 'table 2', 'table 3', 'roberta', 'chatgpt-detector', 'auroc', 'evading ai']):
        print(f"L{i}: {l[:120]}")

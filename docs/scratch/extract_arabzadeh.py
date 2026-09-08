with open(r'C:\Users\olomu\.gemini\antigravity-ide\brain\6235f750-ffe1-4edc-91cb-04c08b593da4\.system_generated\steps\407\content.md', 'r', encoding='utf-8', errors='ignore') as f:
    text = f.read()

print("Length:", len(text))
lines = text.splitlines()

for i, l in enumerate(lines):
    if any(k in l.lower() for k in ['abstract', 'table 1', 'table 2', 'table 3', 'trade-off', 'sparse', 'dense', 'bm25', 'cost', 'latency']):
        if len(l.strip()) > 20:
            print(f"L{i}: {l[:120]}")

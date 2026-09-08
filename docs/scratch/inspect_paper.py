with open(r'C:\Users\olomu\.gemini\antigravity-ide\brain\6235f750-ffe1-4edc-91cb-04c08b593da4\.system_generated\steps\365\content.md', 'r', encoding='utf-8', errors='ignore') as f:
    text = f.read()

print("Length:", len(text))
lines = text.splitlines()
print("Lines:", len(lines))

for i, l in enumerate(lines):
    if any(k in l.lower() for k in ['abstract', 'result', 'discussion', 'accuracy', 'f1', 'precision', 'recall']):
        print(f"L{i}: {l[:100]}")
        if i > 500:
            break

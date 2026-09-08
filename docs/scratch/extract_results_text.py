from bs4 import BeautifulSoup

with open(r'C:\Users\olomu\.gemini\antigravity-ide\brain\6235f750-ffe1-4edc-91cb-04c08b593da4\.system_generated\steps\365\content.md', 'r', encoding='utf-8', errors='ignore') as f:
    html = f.read()

soup = BeautifulSoup(html, 'html.parser')

# Extract sections
recording = False
current_h2 = None

results_text = []

for elem in soup.find_all(['h2', 'h3', 'p']):
    txt = elem.get_text().strip()
    if elem.name == 'h2':
        current_h2 = txt
        if 'Results' in txt or 'Discussion' in txt or 'Conclusion' in txt:
            recording = True
        elif recording and any(k in txt for k in ['Availability', 'Abbreviations', 'References']):
            recording = False
    if recording:
        results_text.append(f"[{elem.name}] {txt}")

print(f"Captured {len(results_text)} elements")
with open(r'C:\Users\olomu\OneDrive\Documents\KOLOXO\AI92\plagiarism-detection\docs\scratch\weber_wulff_extracted.txt', 'w', encoding='utf-8') as f:
    f.write('\n\n'.join(results_text))
print("Saved to weber_wulff_extracted.txt")

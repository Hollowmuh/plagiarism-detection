from bs4 import BeautifulSoup

with open(r'C:\Users\olomu\.gemini\antigravity-ide\brain\6235f750-ffe1-4edc-91cb-04c08b593da4\.system_generated\steps\453\content.md', 'r', encoding='utf-8', errors='ignore') as f:
    html = f.read()

soup = BeautifulSoup(html, 'html.parser')

recording = False
extracted = []

for elem in soup.find_all(['h2', 'h3', 'p']):
    txt = elem.get_text().strip()
    if elem.name in ['h2', 'h3']:
        if any(k in txt for k in ['Workflow process usability', 'Usability results', 'Usability', 'Conclusions and recommendations']):
            recording = True
        elif recording and any(k in txt for k in ['Availability', 'References', 'Acknowledgements']):
            recording = False
    if recording:
        extracted.append(f"[{elem.name}] {txt}")

with open(r'C:\Users\olomu\OneDrive\Documents\KOLOXO\AI92\plagiarism-detection\docs\scratch\foltynek_usability.txt', 'w', encoding='utf-8') as f:
    f.write('\n\n'.join(extracted))

print("Saved foltynek_usability.txt, items:", len(extracted))

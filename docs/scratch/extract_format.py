import sys
sys.stdout.reconfigure(encoding='utf-8')
from docx import Document
from docx.shared import Pt, Inches, Emu

doc = Document(r'C:\Users\olomu\Downloads\fyp\uploads\190407042.docx')

print('=== DOCUMENT STYLE ANALYSIS ===')
styles_used = {}
for p in doc.paragraphs:
    sname = p.style.name if p.style else 'None'
    if sname not in styles_used:
        styles_used[sname] = 0
    styles_used[sname] += 1

for s, c in sorted(styles_used.items(), key=lambda x: -x[1]):
    print(f'  {s}: {c} paragraphs')

print()
print('=== HEADING EXAMPLES ===')
count = 0
for p in doc.paragraphs:
    if p.style and 'Heading' in p.style.name and p.text.strip():
        print(f'[{p.style.name}] {p.text[:80]}')
        count += 1
        if count > 20:
            break

print()
print('=== SECTIONS / PAGE FORMAT ===')
for section in doc.sections:
    print(f'Page width: {section.page_width}, height: {section.page_height}')
    print(f'Margins: top={section.top_margin}, bottom={section.bottom_margin}, left={section.left_margin}, right={section.right_margin}')

print()
print('=== FONT FROM RUNS ===')
for p in doc.paragraphs:
    if p.text.strip():
        for run in p.runs:
            if run.font.name:
                print(f'Font found: {run.font.name}, size={run.font.size}')
                break
        break

# Check body text font
for p in doc.paragraphs:
    if p.style and p.style.name == 'normal' and p.text.strip():
        for run in p.runs:
            if run.text.strip():
                print(f'Body font: name={run.font.name}, size={run.font.size}, bold={run.font.bold}, italic={run.font.italic}')
                break
        break

print()
print('=== LINE SPACING ===')
for p in doc.paragraphs[:10]:
    if p.text.strip():
        pf = p.paragraph_format
        print(f'[{p.style.name}] spacing: before={pf.space_before}, after={pf.space_after}, line_spacing={pf.line_spacing}')

import sys
sys.stdout.reconfigure(encoding='utf-8')
from docx import Document

doc = Document(r'C:\Users\olomu\Downloads\fyp\uploads\Combined_Chapters_1_2_3 (4).docx')
lines = []
for p in doc.paragraphs:
    sname = p.style.name if p.style else 'NoStyle'
    text = p.text.strip()
    if text:
        lines.append(f'[{sname}] {text}')

print(f'TOTAL LINES: {len(lines)}')
print()
for line in lines[:80]:
    print(line)

import sys
sys.stdout.reconfigure(encoding='utf-8')
from docx import Document

doc = Document(r'C:\Users\olomu\Downloads\fyp\uploads\Chapter_4_Results_and_Discussion.docx')

print(f'Total paragraphs: {len(doc.paragraphs)}')
print(f'Total tables: {len(doc.tables)}')
print()

for p in doc.paragraphs:
    sname = p.style.name if p.style else 'NoStyle'
    text = p.text.strip()
    if text and 'Heading' in sname:
        print(f'[{sname}] {text}')

print()
print('=== TABLE TITLES ===')
for i, table in enumerate(doc.tables):
    headers = [c.text for c in table.rows[0].cells]
    print(f'Table {i+1} ({len(table.rows)} rows x {len(table.columns)} cols): {headers[:3]}')

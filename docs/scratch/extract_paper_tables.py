from bs4 import BeautifulSoup
import re

with open(r'C:\Users\olomu\.gemini\antigravity-ide\brain\6235f750-ffe1-4edc-91cb-04c08b593da4\.system_generated\steps\365\content.md', 'r', encoding='utf-8', errors='ignore') as f:
    html = f.read()

soup = BeautifulSoup(html, 'html.parser')

print("Title:", soup.title.string if soup.title else "No title")

# Find headings
for h in soup.find_all(['h1', 'h2', 'h3']):
    print(f"{h.name}: {h.get_text().strip()[:80]}")

# Find tables
tables = soup.find_all('table')
print(f"\nTotal tables found: {len(tables)}")
for i, t in enumerate(tables):
    caption = t.find('caption')
    cap_text = caption.get_text().strip() if caption else "No caption"
    print(f"Table {i+1}: {cap_text[:100]}")
    # Print header and first 2 rows
    rows = t.find_all('tr')
    for r in rows[:3]:
        cells = [c.get_text().strip().replace('\n', ' ') for c in r.find_all(['th', 'td'])]
        print("  ", cells[:6])

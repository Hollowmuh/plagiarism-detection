from bs4 import BeautifulSoup

with open(r'C:\Users\olomu\.gemini\antigravity-ide\brain\6235f750-ffe1-4edc-91cb-04c08b593da4\.system_generated\steps\369\content.md', 'r', encoding='utf-8', errors='ignore') as f:
    html = f.read()

soup = BeautifulSoup(html, 'html.parser')

print("Title:", soup.title.string if soup.title else "No title")

# Find headings
for h in soup.find_all(['h1', 'h2', 'h3']):
    print(f"{h.name}: {h.get_text().strip()[:80]}")

# Find tables or figures
tables = soup.find_all('table')
print(f"Tables: {len(tables)}")
for i, t in enumerate(tables):
    print(f"Table {i+1}: {t.get_text().strip()[:200]}")

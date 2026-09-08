from bs4 import BeautifulSoup

with open(r'C:\Users\olomu\.gemini\antigravity-ide\brain\6235f750-ffe1-4edc-91cb-04c08b593da4\.system_generated\steps\453\content.md', 'r', encoding='utf-8', errors='ignore') as f:
    html = f.read()

soup = BeautifulSoup(html, 'html.parser')

print("Title:", soup.title.string if soup.title else "No title")

# Find headings
for h in soup.find_all(['h1', 'h2', 'h3']):
    print(f"{h.name}: {h.get_text().strip()[:80]}")

# Find sections about LMS, Moodle, latency, turnaround, cross-submission, or tables
for elem in soup.find_all(['h2', 'h3', 'p']):
    txt = elem.get_text().strip()
    if any(k in txt.lower() for k in ['lms', 'moodle', 'turnaround', 'workflow', 'time', 'latency', 'integration', 'submission']):
        if len(txt) > 40:
            print(f"[{elem.name}] {txt[:120]}...")

"""Detector verification v2 — confirms fixes for Bug 1 (preload) and Bug 2 (matches persisted)."""
import requests
import time
from pathlib import Path

API = "http://localhost:8000"
TOKEN = "dev-secret-key-change-in-production"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

SOURCE = """The mitochondrion is a double-membrane-bound organelle found in most eukaryotic cells.
Mitochondria generate most of a cell's supply of adenosine triphosphate.
Cellular respiration occurs inside the mitochondria where glucose is broken down into ATP.
The inner membrane is folded into cristae which increase surface area for ATP production.
Mitochondria are often called the powerhouses of the cell.
Damage to mitochondria is an important factor in human diseases.
"""

COPY = """The mitochondrion is a double-membrane-bound organelle found in most eukaryotic cells.
Mitochondria generate most of a cell's supply of adenosine triphosphate.
These tiny powerhouses are crucial for life as we know it on Earth today.
Cellular respiration occurs inside the mitochondria where glucose is broken down into ATP.
Mitochondria are often called the powerhouses of the cell.
"""

CLEAN = """The Eiffel Tower is a wrought-iron lattice tower in Paris, France.
It was constructed from 1887 to 1889 for the World's Fair.
The tower is 330 metres tall and weighs 10,100 tonnes.
"""


def submit(name: str, content: str) -> str:
    p = Path(name); p.write_text(content, encoding="utf-8")
    with open(p, "rb") as f:
        r = requests.post(f"{API}/api/v1/submissions/", headers=HEADERS,
                          files={"file": (name, f, "text/plain")})
    return r.json()["submission_id"]


def wait(sid: str, max_wait: int = 120) -> dict:
    start = time.time()
    while time.time() - start < max_wait:
        s = requests.get(f"{API}/api/v1/submissions/{sid}/status", headers=HEADERS).json()
        if s["status"] in ("completed", "failed"):
            return s
        time.sleep(2)
    raise TimeoutError(f"{sid} timed out")


def run(name: str, content: str):
    print(f"\n=== {name} ===")
    t0 = time.time()
    sid = submit(name, content)
    final = wait(sid)
    elapsed = time.time() - t0
    if final["status"] != "completed":
        print(f"  FAILED: {final}")
        return
    res = requests.get(f"{API}/api/v1/submissions/{sid}/results", headers=HEADERS).json()
    print(f"  end-to-end: {elapsed:.1f}s")
    print(f"  tier1={res['tier1_score']} tier2={res['tier2_score']} final={res['final_score']}")
    print(f"  plagiarised={res['is_plagiarised']} matches={len(res['matches'])}")
    for m in res["matches"]:
        print(f"    -> source_doc={m['source_document_id']} score={m['similarity_score']} type={m['match_type']}")


if __name__ == "__main__":
    run("v2_source.txt", SOURCE)
    time.sleep(3)
    run("v2_copy.txt", COPY)
    time.sleep(3)
    run("v2_clean.txt", CLEAN)

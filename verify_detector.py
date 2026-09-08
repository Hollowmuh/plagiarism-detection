"""Detector verification: source → exact-copy → clean."""
import requests
import time
import sys
from pathlib import Path

API = "http://localhost:8000"
TOKEN = "dev-secret-key-change-in-production"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

SOURCE = """The mitochondrion is a double-membrane-bound organelle found in most eukaryotic cells.
Mitochondria generate most of a cell's supply of adenosine triphosphate, used as a source of chemical energy.
The word mitochondrion comes from the Greek mitos, meaning thread, and chondrion, meaning granule or grain-like.
Mitochondria have their own independent genome that shows substantial similarity to bacterial genomes.
Cellular respiration occurs inside the mitochondria of eukaryotic cells, where glucose is broken down into ATP.
The inner membrane of the mitochondrion is folded into cristae, which increase the surface area for ATP production.
The matrix is the space enclosed by the inner membrane and contains enzymes used for the citric acid cycle.
Mitochondria are often called the powerhouses of the cell because they generate the energy needed for cellular activity.
The number of mitochondria per cell varies widely by organism, tissue, and cell type.
Damage and subsequent dysfunction in mitochondria is an important factor in a range of human diseases.
"""

COPY = """The mitochondrion is a double-membrane-bound organelle found in most eukaryotic cells.
Mitochondria generate most of a cell's supply of adenosine triphosphate, used as a source of chemical energy.
These organelles are crucial for energy production in living systems and have a fascinating evolutionary history.
The inner membrane of the mitochondrion is folded into cristae, which increase the surface area for ATP production.
Cellular respiration occurs inside the mitochondria of eukaryotic cells, where glucose is broken down into ATP.
Mitochondria are often called the powerhouses of the cell because they generate the energy needed for cellular activity.
"""

CLEAN = """The Eiffel Tower is a wrought-iron lattice tower on the Champ de Mars in Paris, France.
It is named after the engineer Gustave Eiffel, whose company designed and built the tower.
Locally nicknamed "La dame de fer", it was constructed from 1887 to 1889 as the centrepiece of the 1889 World's Fair.
Although initially criticised by some of France's leading artists and intellectuals for its design, it has become a global cultural icon of France.
The tower is 330 metres tall, about the same height as an 81-storey building, and the tallest structure in Paris.
Its base is square, measuring 125 metres on each side. During its construction, the Eiffel Tower surpassed the Washington Monument to become the tallest man-made structure in the world.
"""


def submit(name: str, content: str) -> str:
    p = Path(name)
    p.write_text(content, encoding="utf-8")
    with open(p, "rb") as f:
        r = requests.post(
            f"{API}/api/v1/submissions/",
            headers=HEADERS,
            files={"file": (name, f, "text/plain")},
        )
    print(f"  submit {name}: {r.status_code} {r.json()}")
    r.raise_for_status()
    return r.json()["submission_id"]


def wait(sid: str, max_wait: int = 600) -> dict:
    start = time.time()
    last = None
    while time.time() - start < max_wait:
        r = requests.get(f"{API}/api/v1/submissions/{sid}/status", headers=HEADERS)
        d = r.json()
        if d.get("status") != last:
            print(f"  [{int(time.time()-start)}s] status={d.get('status')} tier_resolved={d.get('tier_resolved')}")
            last = d.get("status")
        if d.get("status") in ("completed", "failed"):
            return d
        time.sleep(3)
    raise TimeoutError(f"submission {sid} did not complete in {max_wait}s")


def results(sid: str) -> dict:
    r = requests.get(f"{API}/api/v1/submissions/{sid}/results", headers=HEADERS)
    print(f"  results HTTP {r.status_code}")
    return r.json()


def run(name: str, content: str) -> dict:
    print(f"\n=== {name} ===")
    sid = submit(name, content)
    final = wait(sid)
    if final.get("status") == "failed":
        print(f"  FAILED: {final}")
        return final
    res = results(sid)
    print(f"  tier1={res.get('tier1_score')} tier2={res.get('tier2_score')} final={res.get('final_score')} plagiarised={res.get('is_plagiarised')} matches={len(res.get('matches', []))} time={res.get('processing_time_ms')}ms")
    if res.get("matches"):
        for m in res["matches"][:3]:
            print(f"    match: {m}")
    return res


if __name__ == "__main__":
    # 1. Source (will be indexed; should have no matches itself since corpus is empty)
    run("source.txt", SOURCE)
    # Brief pause so source is fully indexed
    time.sleep(5)
    # 2. Heavy copy of source (should match high)
    run("copy.txt", COPY)
    time.sleep(3)
    # 3. Unrelated content (should match low/none)
    run("clean.txt", CLEAN)

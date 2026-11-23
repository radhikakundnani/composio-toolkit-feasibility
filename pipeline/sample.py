"""Pick the hand-verification sample BEFORE any extraction runs (fixed seed, 2 per category)."""
import json, random
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
apps = json.loads((ROOT / "data/apps.json").read_text())
rng = random.Random(20261123)
sample = []
for c in range(10):
    sample += rng.sample([a["id"] for a in apps[c*10:(c+1)*10]], 2)
(ROOT / "data/sample.json").write_text(json.dumps({"seed": 20261123, "ids": sorted(sample)}))
print(sorted(sample), [apps[i-1]["app"] for i in sorted(sample)])

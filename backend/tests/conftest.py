import os
import sys
from pathlib import Path

# Tests always run offline, against the mock agents, with short simulated latency.
os.environ["CARTLOG_MOCK"] = "1"
os.environ.setdefault("MOCK_LATENCY_SCALE", "0.2")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

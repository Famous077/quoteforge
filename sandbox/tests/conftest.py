import copy
import json
import sys
from pathlib import Path

import pytest

SANDBOX = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SANDBOX))


@pytest.fixture
def scenario1() -> dict:
    return copy.deepcopy(json.loads((SANDBOX / "examples" / "scenario1.json").read_text()))

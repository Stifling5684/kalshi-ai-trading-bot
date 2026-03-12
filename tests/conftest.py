import sys
from pathlib import Path

import pytest


# Ensure project root is on sys.path so `import src...` works when running pytest locally.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def pytest_collection_modifyitems(config, items):
    """
    Phase 1: limit default test surface to paper-safe tests.

    We keep core safety and deterministic pipeline tests active, and skip
    legacy/Phase 2 tests (agents, LLMs, live trading) by default.
    """
    phase1_safe = {
        "test_verify_paper_safety.py",
        "test_deterministic_filters_ingestion.py",
    }

    for item in items:
        filename = item.fspath.basename

        # Explicit allow-list by test file name
        if filename in phase1_safe:
            continue

        # Skip legacy/Phase 2 tests by default
        item.add_marker(
            pytest.mark.skip(
                reason="Skipped in Phase 1: legacy/Phase 2 test (agents/LLMs/live trading)."
            )
        )


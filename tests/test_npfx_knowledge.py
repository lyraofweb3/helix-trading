from pathlib import Path

from helix.knowledge_loader import load_npfx_excerpt
from helix.config import KNOWLEDGE_VERSION


def test_npfx_synthesis_exists():
    p = Path("helix/knowledge/NETPROFITFX_SYNTHESIS.md")
    assert p.is_file()
    assert "launch a good trade" in p.read_text().lower() or "Six-step" in p.read_text() or "six-step" in p.read_text()


def test_npfx_excerpt_nonzero():
    assert len(load_npfx_excerpt()) > 200


def test_knowledge_version_bumped():
    assert "v4" in KNOWLEDGE_VERSION or "npfx" in KNOWLEDGE_VERSION

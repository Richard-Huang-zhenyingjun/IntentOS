from pathlib import Path


def test_readme_exists():
    """Main README exists and has required sections."""
    assert Path("README.md").exists()
    content = Path("README.md").read_text()
    assert "Quick Start" in content
    assert "Architecture" in content


def test_demo_artifacts_complete():
    """Demo artifacts directory has expected files."""
    assert Path("demo_artifacts/README.md").exists()
    # Check for at least one events file
    assert len(list(Path("demo_artifacts").glob("*_events.jsonl"))) > 0

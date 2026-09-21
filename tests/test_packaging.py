"""requirements.txt and pyproject.toml declare the same dependencies in two places, and CI audits
one of them. If they drift, the audit stops covering what actually gets installed.

Parsed with a regex rather than tomllib so this runs on 3.10 as well as 3.11+.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = (ROOT / "pyproject.toml").read_text()


def _norm(spec: str) -> str:
    return re.sub(r"\s+", "", spec).lower()


def _declared() -> set[str]:
    block = re.search(r"^dependencies\s*=\s*\[(.*?)\]", PYPROJECT, re.S | re.M)
    assert block, "no dependencies array in pyproject.toml"
    body = re.sub(r"#.*", "", block.group(1))
    return {_norm(m) for m in re.findall(r'"([^"]+)"', body)}


def test_requirements_matches_pyproject_dependencies():
    req = {_norm(line) for line in (ROOT / "requirements.txt").read_text().splitlines()
           if line.strip() and not line.lstrip().startswith("#")}
    declared = _declared()
    assert req == declared, (
        "requirements.txt and pyproject.toml disagree — CI audits requirements.txt.\n"
        f"  only in pyproject:    {sorted(declared - req)}\n"
        f"  only in requirements: {sorted(req - declared)}")


def test_version_matches_the_changelog():
    m = re.search(r'^version\s*=\s*"([^"]+)"', PYPROJECT, re.M)
    assert m, "no version in pyproject.toml"
    first = next(line for line in (ROOT / "CHANGELOG.md").read_text().splitlines()
                 if line.startswith("## "))
    assert m.group(1) in first, f"pyproject says {m.group(1)}; newest CHANGELOG entry is {first!r}"


def test_weekly_commit_stages_every_tracked_file_the_pipeline_rewrites():
    """The weekly job listed what to commit by glob, missed outputs/survival*.svg and
    data/documents_seen.csv, and then `git pull --rebase` refused to run over the unstaged changes
    (exit 128) on the first Monday CAISO published new data. `git add -u` must stay in that step."""
    wf = (ROOT / ".github" / "workflows" / "weekly.yml").read_text()
    step = wf[wf.index("name: Commit snapshot"):]
    step = step[:step.index("- name:", 10)] if "- name:" in step[10:] else step
    cmds = [ln.strip() for ln in step.splitlines() if ln.strip().startswith("git ")]
    assert "git add -u" in cmds, cmds
    pull = next(i for i, c in enumerate(cmds) if c.startswith("git pull"))
    assert cmds.index("git add -u") < pull, "tracked changes must be staged before the rebase"
    assert "--autostash" in cmds[pull]

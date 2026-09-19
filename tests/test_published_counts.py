"""The test count a judge reads must be the test count that runs.

README, DEMO and JUDGE each state the suite size. Three hand-typed copies of one number drift
— they did, by seven, the first time the suite grew after they were written. So the number
is counted from the files here and every surface is held to it."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"


def suite_counts():
    offline = live = 0
    for f in sorted(TESTS.glob("test_*.py")):
        src = f.read_text()
        assert not re.search(r"^\s*@pytest\.mark\.parametrize", src, re.M), f"{f.name}: parametrize"
        file_live = re.search(r"^pytestmark\s*=\s*pytest\.mark\.live", src, re.M) is not None
        lines = src.splitlines()
        for i, line in enumerate(lines):
            if re.match(r"^def test_", line):
                decorated = any("pytest.mark.live" in lines[j] for j in range(max(0, i - 3), i))
                if file_live or decorated:
                    live += 1
                else:
                    offline += 1
    node = len(re.findall(r'^test\("', (TESTS / "api.test.mjs").read_text(), re.M))
    return {"offline": offline, "node": node, "live": live, "total": offline + node + live}


def test_the_suite_size_on_every_judge_facing_surface_is_the_suite_size():
    c = suite_counts()
    assert c["offline"] > 90 and c["node"] == 9 and c["live"] >= 5
    readme = (ROOT / "README.md").read_text()
    demo = (ROOT / "DEMO.md").read_text()
    judge = (ROOT / "JUDGE.md").read_text()
    assert f"tests-{c['total']}-" in readme, "README badge"
    assert f"**{c['total']} tests**" in readme, "README prose"
    assert f"{c['offline']} offline" in readme and f"{c['live']} live" in readme
    assert f"**{c['total']}**" in demo and f"{c['offline']} offline" in demo, "DEMO"
    assert f"{c['live']} live" in demo
    assert f"**{c['total']}**" in judge and f"{c['offline']} offline" in judge, "JUDGE"
    assert f"{c['live']} live" in judge

"""Round 9, reviewer B: what a change to this round's new modules needs at release. The
release counts every file of the a5s package but services/ and worker.py as the trusted
core (core/releases.py, _code), and a change to the trusted core needs the release approver,
from outside the team, and assurance's tests (docs/architecture.md, independence). This round
put three demonstration scenarios, two knowledge adapters and the client in the package."""

from __future__ import annotations

import copy

import pytest
import yaml

from a5s.core import releases
from conftest import ROOT

NEW = ["a5s/master_data.py", "a5s/software_delivery.py", "a5s/service_desk.py",
       "a5s/knowledge.py", "a5s/graphify.py", "a5s/client.py"]


@pytest.mark.parametrize("module", NEW)
def test_a_fix_to_a_scenario_or_an_adapter_isnt_a_change_to_the_trusted_core(module):
    built = yaml.safe_load(releases.manifest(ROOT, ROOT / "scenarios" / "sample"))
    assert module in built["parts"]["core"]  # file -> digest, as the trusted core's
    before = copy.deepcopy(built)
    before["parts"]["core"][module] = "0" * 64  # the release before: a one-line fix since
    needed = {n.role for n in releases.needs(built, before)}
    assert releases.ASSURANCE not in needed, (
        f"a fix to {module} needs {sorted(needed)}: the outside approver and assurance's tests, "
        "in every deployment, whichever scenario it runs")


import pytest as _pytest

# Round 9: this reproduces a finding still to fix. Its test moves beside the code it covers
# once its fix lands, and leaves here.
pytestmark = _pytest.mark.xfail(strict=True, reason="round 9: a finding still to fix")

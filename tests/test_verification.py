from structural_engine.design.params import P
from structural_engine.design.verification import DEVIATIONS, NOTES, markdown


def test_every_parameter_has_a_checklist_entry_and_nothing_extra():
    assert set(NOTES) == {d["name"] for d in P.describe()}
    assert all(k in ("code", "proposal") and c in ("high", "medium", "low") for k, c, _ in NOTES.values())


def test_checklist_never_claims_verification():
    md = markdown()
    assert md.count("| NO |") == len(P.describe()) and "| yes |" not in md
    assert len(DEVIATIONS) >= 8

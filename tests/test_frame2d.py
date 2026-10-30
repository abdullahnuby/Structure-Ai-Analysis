"""The frame solver against closed-form solutions (nothing here uses the solver to check itself)."""

import pytest

from structural_engine.frame2d import Frame2D, FrameResult

E, A, I = 30e6, 0.1, 0.002  # kN/m2, m2, m4
W, L = 10.0, 6.0


def beam(n_supports, flags):
    f = Frame2D()
    for k in range(n_supports):
        f.add_node(k, k * L, 0.0)
    for k in range(1, n_supports):
        f.add_member(k, k - 1, k, E, A, I)
    for k, fl in enumerate(flags):
        f.add_support(k, *fl)
    return f


def test_simply_supported_udl():
    f = beam(2, [(True, True, False), (False, True, False)])
    f.add_member_udl(1, qy=-W)
    r = f.solve()
    assert r.moment(1, L / 2) == pytest.approx(W * L**2 / 8)
    assert r.moment(1, 0) == pytest.approx(0, abs=1e-9)
    assert r.reactions[0][1] == pytest.approx(W * L / 2) and r.reactions[1][1] == pytest.approx(
        W * L / 2
    )
    assert r.shear(1, 0) == pytest.approx(W * L / 2) and r.shear(1, L) == pytest.approx(-W * L / 2)


def test_fixed_fixed_udl_fully_restrained_model():
    f = beam(2, [(True, True, True), (True, True, True)])
    f.add_member_udl(1, qy=-W)
    r = f.solve()
    assert r.moment(1, 0) == pytest.approx(-W * L**2 / 12)
    assert r.moment(1, L) == pytest.approx(-W * L**2 / 12)
    assert r.moment(1, L / 2) == pytest.approx(W * L**2 / 24)


def test_two_equal_spans_three_moment_results():
    f = beam(3, [(True, True, False), (False, True, False), (False, True, False)])
    for m in (1, 2):
        f.add_member_udl(m, qy=-W)
    r = f.solve()
    assert r.moment(1, L) == pytest.approx(-W * L**2 / 8)
    assert [r.reactions[k][1] for k in range(3)] == pytest.approx(
        [3 * W * L / 8, 10 * W * L / 8, 3 * W * L / 8]
    )


def test_cantilever_tip_deflection_and_moment():
    f = beam(2, [(True, True, True), (False, False, False)])
    f.add_nodal_load(1, fy=-5.0)
    r = f.solve()
    assert r.displacements[1][1] == pytest.approx(-5.0 * L**3 / (3 * E * I))
    assert r.moment(1, 0) == pytest.approx(-5.0 * L)


def test_vertical_column_axial_force():
    f = Frame2D()
    f.add_node(1, 0, 0)
    f.add_node(2, 0, 3)
    f.add_member("c", 1, 2, E, A, I)
    f.add_support(1, True, True, True)
    f.add_nodal_load(2, fy=-100.0)
    r = f.solve()
    assert r.axial("c", 1.5) == pytest.approx(-100.0)  # compression
    assert r.reactions[1][1] == pytest.approx(100.0)
    assert r.displacements[2][1] == pytest.approx(-100.0 * 3 / (E * A))


def test_inclined_member_equilibrium():
    f = Frame2D()
    f.add_node(1, 0, 0)
    f.add_node(2, 4, 3)  # length 5
    f.add_member("m", 1, 2, E, A, I)
    f.add_support(1, True, True, True)
    f.add_member_udl("m", qy=-10.0)  # global gravity along a 5 m member = 50 kN
    r = f.solve()
    assert r.reactions[1][1] == pytest.approx(50.0)
    assert r.reactions[1][0] == pytest.approx(0.0, abs=1e-9)
    assert r.reactions[1][2] == pytest.approx(100.0)  # 50 kN at x = 2 m from the base


def test_portal_with_stiff_beam_sway():
    h, span, H = 4.0, 6.0, 20.0
    f = Frame2D()
    for nid, xy in {1: (0, 0), 2: (0, h), 3: (span, h), 4: (span, 0)}.items():
        f.add_node(nid, *xy)
    # The closed form (shear H/2 per column, base moment H*h/4) assumes a rigid beam and
    # inextensible columns, so model exactly that: huge A everywhere and a very stiff beam.
    f.add_member("c1", 1, 2, E, A * 1e4, I)
    f.add_member("b", 2, 3, E, A * 1e4, I * 1e4)
    f.add_member("c2", 4, 3, E, A * 1e4, I)
    f.add_support(1, True, True, True)
    f.add_support(4, True, True, True)
    f.add_nodal_load(2, fx=H)
    r = f.solve()
    assert r.reactions[1][0] == pytest.approx(-H / 2, rel=1e-3)
    assert abs(r.reactions[1][2]) == pytest.approx(H * h / 4, rel=1e-3)
    assert r.reactions[1][0] + r.reactions[4][0] == pytest.approx(-H)  # horizontal equilibrium


def test_combine_is_linear():
    f = beam(2, [(True, True, False), (False, True, False)])
    f.add_member_udl(1, qy=-W)
    r = f.solve()
    c = FrameResult.combine([(1.4, r), (1.6, r)])
    assert c.moment(1, L / 2) == pytest.approx(3.0 * r.moment(1, L / 2))
    assert c.reactions[0][1] == pytest.approx(3.0 * r.reactions[0][1])


@pytest.mark.parametrize("bad", ["duplicate_node", "unknown_node", "zero_length", "nonpositive_I"])
def test_model_errors(bad):
    f = Frame2D()
    f.add_node(1, 0, 0)
    f.add_node(2, 1, 0)
    with pytest.raises(ValueError):
        if bad == "duplicate_node":
            f.add_node(1, 5, 5)
        elif bad == "unknown_node":
            f.add_member("m", 1, 99, E, A, I)
        elif bad == "zero_length":
            f.add_node(3, 0, 0)
            f.add_member("m", 1, 3, E, A, I)
        else:
            f.add_member("m", 1, 2, E, A, 0.0)


def test_unstable_and_empty_models_are_rejected():
    f = beam(2, [(True, True, False), (False, False, False)])  # a pin and nothing else: mechanism
    with pytest.raises(ValueError, match="unstable"):
        f.solve()
    with pytest.raises(ValueError, match="no members"):
        Frame2D().solve()

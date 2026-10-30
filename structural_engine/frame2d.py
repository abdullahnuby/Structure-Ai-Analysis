"""Linear-elastic 2D frame solver (direct stiffness method, Euler-Bernoulli members).

Units are the caller's but must be consistent; the design engine uses kN and m
(E in kN/m2, A in m2, I in m4).

Sign conventions
  * global axes: x right, y up; rotations counter-clockwise positive
  * member local x runs from node i to node j, local y is local x rotated +90 degrees
  * member end forces [Ni, Vi, Mi, Nj, Vj, Mj] are the forces the rest of the structure exerts
    ON the member (local axes)
  * ``moment`` returns the sagging bending moment (tension on the local -y side, i.e. the bottom
    of a left-to-right horizontal beam), ``shear`` the internal shear and ``axial`` the internal
    axial force (tension positive)
  * member loads are uniform loads per unit member length given in GLOBAL directions
    (gravity on a horizontal beam is qy < 0)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np


@dataclass
class _Member:
    i: int
    j: int
    E: float
    A: float
    I: float
    L: float
    c: float
    s: float


@dataclass
class FrameResult:
    displacements: dict
    reactions: dict
    member_forces: dict  # id -> np.array([Ni, Vi, Mi, Nj, Vj, Mj])
    member_q: dict  # id -> (qx_local, qy_local)
    member_length: dict

    def moment(self, member, x: float) -> float:
        f, (_, qy) = self.member_forces[member], self.member_q[member]
        return f[1] * x + qy * x * x / 2.0 - f[2]

    def shear(self, member, x: float) -> float:
        f, (_, qy) = self.member_forces[member], self.member_q[member]
        return f[1] + qy * x

    def axial(self, member, x: float) -> float:
        f, (qx, _) = self.member_forces[member], self.member_q[member]
        return -f[0] - qx * x

    @staticmethod
    def combine(terms: list[tuple[float, "FrameResult"]]) -> "FrameResult":
        """Linear combination sum(factor * result) of results of the SAME frame."""
        base = terms[0][1]

        def comb(attr, size):
            out = {}
            for key in getattr(base, attr):
                out[key] = sum(f * np.asarray(getattr(r, attr)[key], dtype=float) for f, r in terms)
            return out

        return FrameResult(
            displacements=comb("displacements", 3),
            reactions=comb("reactions", 3),
            member_forces=comb("member_forces", 6),
            member_q={k: tuple(v) for k, v in comb("member_q", 2).items()},
            member_length=dict(base.member_length),
        )


class Frame2D:
    def __init__(self) -> None:
        self.nodes: dict = {}
        self.members: dict = {}
        self.supports: dict = {}
        self.nodal_loads: dict = {}
        self.member_loads: dict = {}

    # ---- model -------------------------------------------------------------------------------
    def add_node(self, nid, x: float, y: float) -> None:
        if nid in self.nodes:
            raise ValueError(f"Duplicate node {nid}")
        self.nodes[nid] = (float(x), float(y))

    def add_member(self, mid, ni, nj, E: float, A: float, I: float) -> None:
        if mid in self.members:
            raise ValueError(f"Duplicate member {mid}")
        for n in (ni, nj):
            if n not in self.nodes:
                raise ValueError(f"Member {mid}: unknown node {n}")
        if min(E, A, I) <= 0:
            raise ValueError(f"Member {mid}: E, A and I must be positive")
        (x1, y1), (x2, y2) = self.nodes[ni], self.nodes[nj]
        length = math.hypot(x2 - x1, y2 - y1)
        if length <= 0:
            raise ValueError(f"Member {mid} has zero length")
        self.members[mid] = _Member(ni, nj, E, A, I, length, (x2 - x1) / length, (y2 - y1) / length)

    def add_support(self, nid, ux: bool = True, uy: bool = True, rz: bool = False) -> None:
        if nid not in self.nodes:
            raise ValueError(f"Unknown node {nid}")
        self.supports[nid] = (bool(ux), bool(uy), bool(rz))

    def add_nodal_load(self, nid, fx: float = 0.0, fy: float = 0.0, m: float = 0.0) -> None:
        old = self.nodal_loads.get(nid, (0.0, 0.0, 0.0))
        self.nodal_loads[nid] = (old[0] + fx, old[1] + fy, old[2] + m)

    def add_member_udl(self, mid, qx: float = 0.0, qy: float = 0.0) -> None:
        old = self.member_loads.get(mid, (0.0, 0.0))
        self.member_loads[mid] = (old[0] + qx, old[1] + qy)

    # ---- helpers -----------------------------------------------------------------------------
    @staticmethod
    def _k_local(m: _Member) -> np.ndarray:
        E, A, I, L = m.E, m.A, m.I, m.L
        a, b = E * A / L, E * I / L**3
        return np.array(
            [
                [a, 0, 0, -a, 0, 0],
                [0, 12 * b, 6 * b * L, 0, -12 * b, 6 * b * L],
                [0, 6 * b * L, 4 * b * L * L, 0, -6 * b * L, 2 * b * L * L],
                [-a, 0, 0, a, 0, 0],
                [0, -12 * b, -6 * b * L, 0, 12 * b, -6 * b * L],
                [0, 6 * b * L, 2 * b * L * L, 0, -6 * b * L, 4 * b * L * L],
            ]
        )

    @staticmethod
    def _T(m: _Member) -> np.ndarray:
        c, s = m.c, m.s
        r = np.array([[c, s, 0], [-s, c, 0], [0, 0, 1]])
        t = np.zeros((6, 6))
        t[:3, :3] = r
        t[3:, 3:] = r
        return t

    def _local_q(self, mid, m: _Member):
        qx, qy = self.member_loads.get(mid, (0.0, 0.0))
        return m.c * qx + m.s * qy, -m.s * qx + m.c * qy

    @staticmethod
    def _fixed_end(m: _Member, qlx: float, qly: float) -> np.ndarray:
        L = m.L
        return np.array(
            [
                -qlx * L / 2,
                -qly * L / 2,
                -qly * L * L / 12,
                -qlx * L / 2,
                -qly * L / 2,
                qly * L * L / 12,
            ]
        )

    # ---- solve -------------------------------------------------------------------------------
    def solve(self) -> FrameResult:
        if not self.members:
            raise ValueError("The frame has no members")
        ids = list(self.nodes)
        index = {nid: k for k, nid in enumerate(ids)}
        n_dof = 3 * len(ids)
        K = np.zeros((n_dof, n_dof))
        F = np.zeros(n_dof)
        for nid, (fx, fy, mz) in self.nodal_loads.items():
            F[3 * index[nid] : 3 * index[nid] + 3] += (fx, fy, mz)
        per_member = {}
        for mid, m in self.members.items():
            t, k = self._T(m), self._k_local(m)
            ql = self._local_q(mid, m)
            f0 = self._fixed_end(m, *ql)
            dofs = [3 * index[m.i] + r for r in range(3)] + [3 * index[m.j] + r for r in range(3)]
            K[np.ix_(dofs, dofs)] += t.T @ k @ t
            F[dofs] += -t.T @ f0
            per_member[mid] = (t, k, f0, ql, dofs)
        restrained = np.zeros(n_dof, dtype=bool)
        for nid, flags in self.supports.items():
            for r, flag in enumerate(flags):
                restrained[3 * index[nid] + r] = flag
        free = ~restrained
        u = np.zeros(n_dof)
        if free.any():  # a fully restrained model is legitimate: u = 0, only reactions to find
            kff = K[np.ix_(free, free)]
            if np.linalg.matrix_rank(kff) < kff.shape[0]:
                raise ValueError(
                    "The structure is unstable (insufficient or badly placed supports)"
                )
            u[free] = np.linalg.solve(kff, F[free])
        reaction = K @ u - F
        forces, qloc, lengths = {}, {}, {}
        for mid, (t, k, f0, ql, dofs) in per_member.items():
            forces[mid] = k @ (t @ u[dofs]) + f0
            qloc[mid] = ql
            lengths[mid] = self.members[mid].L
        return FrameResult(
            displacements={nid: u[3 * index[nid] : 3 * index[nid] + 3].copy() for nid in ids},
            reactions={
                nid: np.where(
                    restrained[3 * index[nid] : 3 * index[nid] + 3],
                    reaction[3 * index[nid] : 3 * index[nid] + 3],
                    0.0,
                )
                for nid in ids
            },
            member_forces=forces,
            member_q=qloc,
            member_length=lengths,
        )

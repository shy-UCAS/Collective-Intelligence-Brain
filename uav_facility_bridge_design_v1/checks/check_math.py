"""Independent local algebra checks. This is not a UAV prediction service.

Run: python checks/check_math.py --report checks/math_report.json
The tests concern frozen linear pieces, not global nonlinear swarm inference.
"""
from __future__ import annotations
import argparse
import json
import time
from importlib.metadata import version
from pathlib import Path
from typing import Callable
import numpy as np
from numpy.testing import assert_allclose
from scipy.integrate import quad_vec
from scipy.linalg import expm, solve


def affine_step(a: np.ndarray, h: np.ndarray, dt: float) -> tuple[np.ndarray, np.ndarray]:
    if dt < 0 or not np.isfinite(dt):
        raise ValueError('dt must be finite and nonnegative')
    n = len(h)
    m = np.zeros((n + 1, n + 1))
    m[:n, :n] = a
    m[:n, n] = h
    e = expm(m * dt)
    return e[:n, :n], e[:n, n]


def discrete_noise(a: np.ndarray, qc: np.ndarray, dt: float) -> np.ndarray:
    n = a.shape[0]
    block = np.block([[a, qc], [np.zeros_like(a), -a.T]])
    e = expm(block * dt)
    q = e[:n, n:] @ e[:n, :n].T
    return (q + q.T) / 2


def matrices(n: int, alpha: float = 0.06, gamma: float = 0.04):
    eye = np.eye(n)
    j = np.ones((n, n)) / n - eye
    az = np.block([[-gamma * eye, eye], [np.zeros((n, n)), alpha * j]])
    c = np.block([[eye, np.zeros((n, n))], [-gamma * eye, eye]])
    cinv = np.block([[eye, np.zeros((n, n))], [gamma * eye, eye]])
    ax = np.block([[np.zeros((n, n)), eye], [alpha * gamma * j, alpha * j - gamma * eye]])
    return az, c, cinv, ax


def test_physical_state_transform() -> None:
    rng = np.random.default_rng(27)
    for n in (1, 2, 5):
        az, c, cinv, ax = matrices(n)
        dest, gamma, beta = 234.5, 0.04, 0.06
        r = rng.normal(size=n)
        hz = np.r_[np.full(n, gamma * dest), beta * r]
        b = np.r_[np.zeros(n), np.full(n, gamma * dest)]
        hx = np.r_[np.zeros(n), beta * r]
        assert_allclose(c @ az @ cinv, ax, atol=1e-12)
        assert_allclose(c @ hz - ax @ b, hx, atol=1e-12)
        z = rng.normal(size=2*n)
        x = c @ z + b
        assert_allclose(c @ (az @ z + hz), ax @ x + hx, atol=1e-12)
        fz, mz = affine_step(az, hz, 0.8)
        fx, mx = affine_step(ax, hx, 0.8)
        assert_allclose(c @ (fz @ z + mz) + b, fx @ x + mx, atol=1e-10)


def test_covariance_transform() -> None:
    _, c, cinv, _ = matrices(1)
    covz = np.diag([100.0, 5.0])
    covx = c @ covz @ c.T
    assert_allclose(covx, [[100.0, -4.0], [-4.0, 5.16]], atol=1e-12)
    assert_allclose(cinv @ covx @ cinv.T, covz, atol=1e-12)


def test_single_member_and_singular_matrix() -> None:
    _, _, _, a1 = matrices(1)
    assert_allclose(a1, [[0, 1], [0, -0.04]], atol=1e-12)
    for n in (1, 3, 5):
        az, _, _, ax = matrices(n)
        assert np.linalg.matrix_rank(az, tol=1e-10) < 2*n
        assert np.linalg.matrix_rank(ax, tol=1e-10) < 2*n


def test_mean_sign_against_sde() -> None:
    gamma, dest, dt = 0.04, 100.0, 2.0
    a, h = np.array([[-gamma]]), np.array([gamma*dest])
    _, m = affine_step(a, h, dt)
    expected = (1 - np.exp(-gamma*dt)) * dest
    assert_allclose(m[0], expected, atol=1e-12)
    printed_expression = ((np.eye(1)-expm(a*dt)) @ solve(a, h))[0]
    assert_allclose(printed_expression, -expected, atol=1e-12)
    assert m[0] > 0 and printed_expression < 0


def test_affine_integral_with_singular_a() -> None:
    _, _, _, a = matrices(3)
    h = np.array([0, 0, 0, 0.2, -0.1, -0.1])
    _, m = affine_step(a, h, 1.7)
    direct, _ = quad_vec(lambda s: expm(a*s) @ h, 0, 1.7)
    assert_allclose(m, direct, atol=1e-11)


def test_noise_integral_and_semigroup() -> None:
    _, _, _, a = matrices(2)
    l = np.vstack([np.zeros((2, 2)), np.eye(2)*0.7])
    qc = l @ l.T
    q = discrete_noise(a, qc, 1.3)
    direct, _ = quad_vec(lambda s: expm(a*s) @ qc @ expm(a.T*s), 0, 1.3)
    assert_allclose(q, direct, atol=1e-11)
    assert np.linalg.eigvalsh(q).min() >= -1e-11
    f2 = expm(a*0.8)
    composed = f2 @ discrete_noise(a, qc, 0.5) @ f2.T + discrete_noise(a, qc, 0.8)
    assert_allclose(q, composed, atol=1e-11)


def test_bridge_gaussian_equivalence() -> None:
    rng = np.random.default_rng(34)
    for n in (2, 4):
        bh, bb = rng.normal(size=(n, n)), rng.normal(size=(n, n))
        qh = bh @ bh.T + np.eye(n)
        qb = bb @ bb.T + np.eye(n)
        f = rng.normal(size=(n, n))
        mu, target, mb = rng.normal(size=(3, n))
        s = f @ qh @ f.T + qb
        gain = solve(s, f @ qh, assume_a='pos').T
        cov = qh - gain @ f @ qh
        mean = mu + gain @ (target - f @ mu - mb)
        precision = solve(qh, np.eye(n), assume_a='pos') + f.T @ solve(qb, f, assume_a='pos')
        cov_info = solve(precision, np.eye(n), assume_a='pos')
        mean_info = cov_info @ (solve(qh, mu, assume_a='pos') + f.T @ solve(qb, target-mb, assume_a='pos'))
        assert_allclose(cov, cov_info, atol=1e-10)
        assert_allclose(mean, mean_info, atol=1e-10)
        assert np.linalg.eigvalsh(cov).min() > 0


def test_bridge_endpoint_limit() -> None:
    # Brownian bridge: a simple exact case for the limit, not a swarm model.
    eye = np.eye(2)
    qh = 0.7*eye
    mu, target = np.array([0.2, -0.1]), np.array([3.0, 1.0])
    eps = 1e-7
    gain = solve(qh + eps*eye, qh, assume_a='pos').T
    conditional_mean = mu + gain @ (target-mu)
    conditional_cov = qh-gain @ qh
    assert_allclose(conditional_mean, target, atol=1e-6)
    assert np.trace(conditional_cov) < 1e-6


def test_time_prior_mass_conservation() -> None:
    pi0, likelihood0, likelihood_facility = 0.5, 0.9, 1.7
    totals = []
    for edges in (np.linspace(1, 601, 8), np.linspace(1, 601, 102), np.array([1, 3, 11, 91, 601])):
        masses = np.diff(edges)/(edges[-1]-edges[0])
        assert_allclose(masses.sum(), 1.0)
        joint = (1-pi0) * masses * likelihood_facility
        normalizer = pi0*likelihood0 + joint.sum()
        totals.append(joint.sum()/normalizer)
    assert_allclose(totals, np.full(3, totals[0]), atol=1e-12)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    tests: list[Callable[[], None]] = [test_physical_state_transform, test_covariance_transform,
        test_single_member_and_singular_matrix, test_mean_sign_against_sde,
        test_affine_integral_with_singular_a, test_noise_integral_and_semigroup,
        test_bridge_gaussian_equivalence, test_bridge_endpoint_limit, test_time_prior_mass_conservation]
    results = []
    for fn in tests:
        start = time.perf_counter()
        try:
            fn()
            row = {'check':fn.__name__, 'status':'PASS'}
        except Exception as exc:
            row = {'check':fn.__name__, 'status':'FAIL', 'error':repr(exc)}
        row['elapsedSeconds'] = round(time.perf_counter()-start, 6)
        results.append(row)
        print(row['status'], row['check'])
    report = {'scope':'Local algebra only; not a complete inference or accuracy test',
        'packages':{name:version(name) for name in ['numpy','scipy']}, 'checks':results,
        'passed':sum(x['status']=='PASS' for x in results), 'total':len(results)}
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
    return 0 if report['passed']==report['total'] else 1

if __name__ == '__main__':
    raise SystemExit(main())

"""Build a scan plan from validated config.

Pure data transformation. Stdlib only; no subprocess, no os, no networking
-- same engine-purity invariant as rigging's plan.py.
"""
from __future__ import annotations

from dataclasses import dataclass

from hull import config, scanners


@dataclass(frozen=True)
class Job:
    """One scan job for the configured scanner. No matrix -- a scanner run
    is a single pass over the repo, not one per version."""

    id: str
    runs_on: str
    steps: tuple[scanners.Step, ...]


@dataclass(frozen=True)
class ScanPlan:
    """The full scan plan: one job for the configured scanner."""

    name: str
    permissions: tuple[str, ...]
    jobs: tuple[Job, ...]
    #: Branches whose pushes trigger the workflow. See config.Config.
    push_branches: tuple[str, ...] = config.DEFAULT_PUSH_BRANCHES


#: The checkout pin, named rather than inlined so tests (and
#: scripts/sync_action_pins.py) have one place to read it from. rigging's
#: plan.py has had CHECKOUT_STEP for the same reason; hull inlining it is
#: why hull's tests used to restate the SHA literal in four places.
CHECKOUT_USES = "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"
CHECKOUT_VERSION = "v7"


def _scan_env(spec: scanners.ScannerSpec, license_secret) -> dict:
    """The scan step's env mapping: the scanner's own registry env, plus the
    license reference when one is configured.

    When `license_secret` is None -- the case for every config written before
    the key existed -- this returns a mapping equal to `spec.env` itself, so
    the rendered workflow stays byte-identical to what hull emitted before
    (the golden file asserts exactly that). When it is set, one entry is
    APPENDED, so GITHUB_TOKEN keeps its position and only new lines appear in
    the diff; dicts preserve insertion order and the renderer walks them in
    that order, which is what makes the output deterministic.

    The value is assembled here rather than stored anywhere: hull only ever
    holds the secret's NAME, and turns it into a `${{ secrets.<NAME> }}`
    reference GitHub resolves at run time. The name has already been through
    config.SECRET_NAME_RE by this point, which is what makes this the only
    safe place to build an Actions expression out of user input.
    """
    env = dict(spec.env)
    if license_secret is not None and spec.license_env is not None:
        env[spec.license_env] = "${{ secrets." + license_secret + " }}"
    return env


def _build_job(scanner_id: str, license_secret=None) -> Job:
    spec = scanners.REGISTRY[scanner_id]
    checkout_step = scanners.Step(
        uses=CHECKOUT_USES,
        uses_version=CHECKOUT_VERSION,
        with_={"fetch-depth": spec.checkout_fetch_depth},
    )
    scan_step = scanners.Step(uses=spec.action_ref,
                              env=_scan_env(spec, license_secret),
                              with_=spec.scan_with,
                              uses_version=spec.action_ref_version)
    return Job(
        id=spec.id,
        runs_on="ubuntu-latest",
        steps=(checkout_step, scan_step),
    )


def build_plan(cfg: config.Config) -> ScanPlan:
    job = _build_job(cfg.scanner, cfg.license_secret)
    return ScanPlan(name=cfg.name,
                    permissions=scanners.REGISTRY[cfg.scanner].permissions,
                    jobs=(job,),
                    push_branches=cfg.push_branches)

import json
import pytest
from keel import ghio
from keel.facts import Tri


@pytest.fixture(autouse=True)
def clear():
    ghio.clear_cache()
    yield
    ghio.clear_cache()


class FakeProc:
    def __init__(self, stdout, returncode=0):
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = ""


def test_pr_facts_parses_single_call(monkeypatch):
    calls = []

    def fake_run(args, **kw):
        calls.append(args)
        return FakeProc(json.dumps({
            "baseRefName": "develop",
            "headRefName": "feature/x",
            "isCrossRepository": True,
            "reviewDecision": "APPROVED",
            "reviews": [{"state": "APPROVED"}],
        }))

    monkeypatch.setattr(ghio.subprocess, "run", fake_run)
    facts = ghio.pr_facts("5")
    assert facts == {"base": "develop", "head": "feature/x",
                     "is_fork": Tri.TRUE, "review_state": "APPROVED"}
    assert len(calls) == 1, "must be a single gh call"


def test_pr_facts_is_cached(monkeypatch):
    calls = []
    monkeypatch.setattr(ghio.subprocess, "run",
                        lambda args, **kw: calls.append(args) or FakeProc(json.dumps(
                            {"baseRefName": "develop", "headRefName": "f",
                             "isCrossRepository": False, "reviewDecision": None,
                             "reviews": []})))
    ghio.pr_facts("5")
    ghio.pr_facts("5")
    assert len(calls) == 1


def test_commented_review_surfaces_when_no_decision(monkeypatch):
    monkeypatch.setattr(ghio.subprocess, "run", lambda args, **kw: FakeProc(json.dumps({
        "baseRefName": "develop", "headRefName": "feature/x",
        "isCrossRepository": False, "reviewDecision": None,
        "reviews": [{"state": "COMMENTED"}],
    })))
    assert ghio.pr_facts("5")["review_state"] == "COMMENTED"


def test_changes_requested_wins_over_comment(monkeypatch):
    monkeypatch.setattr(ghio.subprocess, "run", lambda args, **kw: FakeProc(json.dumps({
        "baseRefName": "develop", "headRefName": "feature/x",
        "isCrossRepository": False, "reviewDecision": "CHANGES_REQUESTED",
        "reviews": [{"state": "COMMENTED"}],
    })))
    assert ghio.pr_facts("5")["review_state"] == "CHANGES_REQUESTED"


def test_review_state_ignores_non_dict_review_entries(monkeypatch):
    # A malformed/unexpected `reviews[]` element (e.g. gh emitting a bare
    # string, or a future schema change) must not raise -- degrade to
    # ignoring that entry rather than crashing the hook.
    monkeypatch.setattr(ghio.subprocess, "run", lambda args, **kw: FakeProc(json.dumps({
        "baseRefName": "develop", "headRefName": "feature/x",
        "isCrossRepository": False, "reviewDecision": None,
        "reviews": ["not-a-dict", {"state": "APPROVED"}],
    })))
    assert ghio.pr_facts("5")["review_state"] == "APPROVED"


def test_gh_failure_returns_none(monkeypatch):
    monkeypatch.setattr(ghio.subprocess, "run", lambda args, **kw: FakeProc("", 1))
    assert ghio.pr_facts("5") is None


def test_gh_missing_returns_none(monkeypatch):
    def boom(args, **kw):
        raise OSError("gh not found")
    monkeypatch.setattr(ghio.subprocess, "run", boom)
    assert ghio.pr_facts("5") is None


def test_malformed_json_returns_none(monkeypatch):
    monkeypatch.setattr(ghio.subprocess, "run", lambda args, **kw: FakeProc("{not json"))
    assert ghio.pr_facts("5") is None


@pytest.mark.parametrize("perm,expected", [
    ("ADMIN", Tri.TRUE), ("MAINTAIN", Tri.TRUE), ("WRITE", Tri.TRUE),
    ("READ", Tri.FALSE), ("TRIAGE", Tri.FALSE),
])
def test_capability_from_viewer_permission(monkeypatch, perm, expected):
    monkeypatch.setattr(ghio.subprocess, "run", lambda args, **kw: FakeProc(
        json.dumps({"viewerPermission": perm})))
    assert ghio.capability() is expected


def test_capability_never_requests_raw_jq_output(monkeypatch):
    # Regression: `-q .viewerPermission` makes gh emit a bare word, which is
    # not valid JSON, so json.loads always failed and this path never worked.
    seen = []
    monkeypatch.setattr(ghio.subprocess, "run",
                        lambda args, **kw: seen.append(args) or FakeProc(
                            json.dumps({"viewerPermission": "ADMIN"})))
    ghio.capability()
    assert "-q" not in seen[0], "capability() must parse JSON, not jq output"


def test_capability_unknown_when_field_absent(monkeypatch):
    # `--json viewerPermission` can only return that field, so any other shape
    # means the call did not give us an answer. Unknown, not a guess.
    monkeypatch.setattr(ghio.subprocess, "run",
                        lambda args, **kw: FakeProc(json.dumps({})))
    assert ghio.capability() is Tri.UNKNOWN


def test_capability_unknown_when_field_is_null(monkeypatch):
    monkeypatch.setattr(ghio.subprocess, "run", lambda args, **kw: FakeProc(
        json.dumps({"viewerPermission": None})))
    assert ghio.capability() is Tri.UNKNOWN


def test_capability_unknown_on_failure(monkeypatch):
    monkeypatch.setattr(ghio.subprocess, "run", lambda args, **kw: FakeProc("", 1))
    assert ghio.capability() is Tri.UNKNOWN


def test_every_call_passes_a_timeout(monkeypatch):
    seen = {}
    monkeypatch.setattr(ghio.subprocess, "run",
                        lambda args, **kw: seen.update(kw) or FakeProc("{}"))
    ghio.capability()
    assert "timeout" in seen and seen["timeout"] > 0


# --- cross-repo commands -------------------------------------------------
#
# Action.repo was parsed from `--repo`/`-R`, stored, and then read by
# nothing. `gh pr merge 5 --repo other/org-repo` was therefore evaluated
# against THIS repo's PR #5 -- a different PR, possibly a different base,
# possibly nonexistent -- so the review and merge-strategy gates produced a
# confidently wrong answer rather than an honest unknown.


def test_pr_facts_passes_repo_through_to_gh(monkeypatch):
    calls = []

    def fake_run(args, **kw):
        calls.append(args)
        return FakeProc(json.dumps({"baseRefName": "main", "headRefName": "f",
                                    "isCrossRepository": False}))

    monkeypatch.setattr(ghio.subprocess, "run", fake_run)
    ghio.pr_facts("5", repo="other/org-repo")
    assert "--repo" in calls[0]
    assert calls[0][calls[0].index("--repo") + 1] == "other/org-repo"


def test_capability_passes_repo_through_to_gh(monkeypatch):
    # `gh repo view` takes the repository as a POSITIONAL -- there is no
    # --repo flag on this subcommand, unlike `gh pr view`. Verified against
    # `gh repo view --help`: "USAGE gh repo view [<repository>] [flags]".
    calls = []

    def fake_run(args, **kw):
        calls.append(args)
        return FakeProc(json.dumps({"viewerPermission": "ADMIN"}))

    monkeypatch.setattr(ghio.subprocess, "run", fake_run)
    ghio.capability(repo="other/org-repo")
    assert calls[0][:3] == ["gh", "repo", "view"]
    assert calls[0][3] == "other/org-repo"


def test_no_repo_flag_when_repo_is_none(monkeypatch):
    calls = []

    def fake_run(args, **kw):
        calls.append(args)
        return FakeProc(json.dumps({"baseRefName": "main", "headRefName": "f",
                                    "isCrossRepository": False}))

    monkeypatch.setattr(ghio.subprocess, "run", fake_run)
    ghio.pr_facts("5")
    assert "--repo" not in calls[0]


def test_cache_key_distinguishes_repos(monkeypatch):
    # Without repo in the cache key, the first repo's answer would be
    # served for the second -- the same wrong-repo bug, one layer down.
    payloads = {
        "a/one": {"baseRefName": "main", "headRefName": "f1",
                  "isCrossRepository": False},
        "b/two": {"baseRefName": "develop", "headRefName": "f2",
                  "isCrossRepository": False},
    }

    def fake_run(args, **kw):
        repo = args[args.index("--repo") + 1]
        return FakeProc(json.dumps(payloads[repo]))

    monkeypatch.setattr(ghio.subprocess, "run", fake_run)
    assert ghio.pr_facts("5", repo="a/one")["head"] == "f1"
    assert ghio.pr_facts("5", repo="b/two")["head"] == "f2"

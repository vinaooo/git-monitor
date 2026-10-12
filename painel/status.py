from dataclasses import dataclass, field
from collections import namedtuple
from typing import Optional

CI_STATES = ('success', 'failure', 'running', 'cancelled', 'none')


@dataclass(frozen=True)
class RepoStatus:
    name: str
    url: str = ''
    issues: int = 0
    prs: int = 0
    ci: str = 'none'  # worst CI state, see health.summarize_ci
    error: Optional[str] = None
    ci_counts: dict = field(default_factory=dict)   # {failure, running, cancelled, success}
    pr_counts: dict = field(default_factory=dict)   # {changes, failing, conflict, waiting, approved, draft}
    pr_detail: bool = True                          # False: provider could not tell review states (GitHub, no token)
    details: dict = field(default_factory=dict)     # {bucket: [short labels]} for tooltips
    # optional card signals (signals.py); None = disabled, unavailable or not known
    dependabot: Optional[int] = None                # open Dependabot alerts
    code_scanning: Optional[int] = None             # open code scanning alerts (100 = at least)
    unresolved: Optional[int] = None                # unresolved review threads on open PRs
    release: Optional[str] = None                   # latest release tag
    released_at: Optional[str] = None               # ISO time of that release
    pushed_at: Optional[str] = None                 # ISO time of the last push


RepoInfo = namedtuple('RepoInfo', 'path fork archived private')  # one entry of an account's repository listing

from dataclasses import dataclass
from typing import Optional

CI_STATES = ('success', 'failure', 'running', 'cancelled', 'none')


@dataclass(frozen=True)
class RepoStatus:
    name: str
    url: str = ''
    issues: int = 0
    prs: int = 0
    ci: str = 'none'
    error: Optional[str] = None

"""Pure CI-transition detection and the on-disk last-known state (no GTK)."""
import json
import os

KINDS = ('failed', 'recovered', 'broke_running')


def step(entry, ci):
    """entry: stored {ci, settled} or None; ci: new CI state. Returns (new entry, kind | None).
    `settled` is the last success/failure, so a running phase between two results doesn't hide a transition."""
    new = {'ci': ci, 'settled': ci if ci in ('success', 'failure') else (entry or {}).get('settled', 'none')}
    if entry is None:  # first sight of this repo: record, never notify
        return new, None
    kind = None
    if ci == 'failure' and entry['settled'] != 'failure':
        kind = 'broke_running' if entry['ci'] == 'running' else 'failed'
    elif ci == 'success' and entry['settled'] == 'failure':
        kind = 'recovered'
    return new, kind


def wanted(kind, enabled):
    return kind is not None and kind in enabled


def ci_url(base):
    if not base:
        return ''
    return f'{base}/actions' if 'github.com' in base else f'{base}/-/pipelines'


class StateStore:
    """{repo: {ci, settled}} in a JSON file; a missing or corrupt file reads as empty."""

    def __init__(self, path):
        self.path = path
        try:
            with open(path) as f:
                self.data = json.load(f)
        except (OSError, ValueError):
            self.data = {}
        if not isinstance(self.data, dict):
            self.data = {}

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(self.data, f)
        os.replace(tmp, self.path)

    def forget(self, repo):
        if self.data.pop(repo, None) is not None:
            self.save()

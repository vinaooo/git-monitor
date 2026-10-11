# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Painel: GNOME/GTK4 + libadwaita app (Python/PyGObject, meson, Flatpak) showing one card per GitHub/GitLab repo: open issues, pending PRs/MRs, CI state, open-in-browser. No third-party Python deps (stdlib `urllib` only).

## Commands

- Tests (stdlib `unittest`, no deps; write the failing test first): `python3 -m unittest discover -s tests -t .`; single: `python3 -m unittest tests.test_gitlab.GitLabTest.test_counts_and_name`
- Run from source (no tree-run support, must install to a prefix):
  ```
  meson setup build --prefix=$PWD/_prefix && meson install -C build
  GSETTINGS_SCHEMA_DIR=_prefix/share/glib-2.0/schemas XDG_DATA_DIRS=_prefix/share:/usr/share _prefix/bin/painel
  ```
- Flatpak: `flatpak-builder --user --install --force-clean build-flatpak io.github.vina.Painel.yml`, then `flatpak run io.github.vina.Painel`
- Lint: `desktop-file-validate data/*.desktop`, `appstreamcli validate --no-net data/*.metainfo.xml`
- `build/`, `_prefix/`, `build-flatpak/`, `.flatpak-builder/` are throwaway; delete after use.

## Architecture

Package `painel/` (installed to `<prefix>/share/painel/painel/`; new modules must be added to `painel/meson.build`). Launcher template: `src/painel.in`. Dependencies point inward: UI -> `service` -> providers -> `HttpClient` port; only `tokens.py` and the UI import GTK/libsecret, so everything else is unit-testable with `tests/fakes.py:FakeHttp`.

- `repo_id.py` — repo identity string `host/path` (`github.com/o/r`, `gitlab.com/g/sub/p`): `parse` (bare `o/r` = GitHub; GitLab only for `gitlab.com` / `gitlab.*`), `migrate` (legacy bare `o/r` entries), `host_of`.
- `status.py` — `RepoStatus` frozen dataclass; the only shape UI consumes. CI vocabulary: `success|failure|running|cancelled|none`.
- `http.py` — `HttpClient` port, `UrllibClient`, `HttpError(code)`, `NetworkError`. Redirects to another host strip `Authorization`/`PRIVATE-TOKEN` (urllib forwards them by default); keep that when touching the client.
- `github.py` / `gitlab.py` — `fetch(path, token) -> RepoStatus`, raise on failure. Deliberate quirks: GitHub `open_issues_count` includes PRs (issues = count - PRs, PR count from search API); GitLab project payload omits the issue count when anonymous (use `/issues_statistics`), MR count is the `X-Total` header, GitLab statuses mapped in `_CI`.
- `service.py` — `StatusService`: host -> provider, converts every failure into `RepoStatus(error=...)`. Add a provider = new module + branch in `_provider` + tests.
- `tokens.py` — `TokenStore` (libsecret, keyed by `host`; legacy `purpose=github-token` fallback). Never store tokens in GSettings/files; keyring failures raise `TokenStoreError` (no plaintext fallback).
- `window.py` / `card.py` / `prefs.py` / `main.py` — UI. `App` builds `StatusService` and `TokenStore` and injects them into `Window`. One daemon thread per repo per refresh, results return via `GLib.idle_add`; cards removed mid-fetch are ignored. GSettings keys: `repos`, `refresh-seconds`.

## Open items before Flathub submission

App ID `io.github.vina.Painel` is a placeholder (must match a real repo/domain), plus missing screenshots and metainfo `<developer>` tag.

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Painel: GNOME/GTK4 + libadwaita app (Python/PyGObject, meson, Flatpak) showing one card per GitHub/GitLab repo: open issues, pending PRs/MRs, CI state, open-in-browser. No third-party Python deps (stdlib `urllib` only).

## Commands

- Self-check (the only test; asserts for `parse`/`migrate`): `python3 -I src/providers.py`
- Run from source (no tree-run support, must install to a prefix):
  ```
  meson setup build --prefix=$PWD/_prefix && meson install -C build
  GSETTINGS_SCHEMA_DIR=_prefix/share/glib-2.0/schemas XDG_DATA_DIRS=_prefix/share:/usr/share _prefix/bin/painel
  ```
- Flatpak: `flatpak-builder --user --install --force-clean build-flatpak io.github.vina.Painel.yml`, then `flatpak run io.github.vina.Painel`
- Lint: `desktop-file-validate data/*.desktop`, `appstreamcli validate --no-net data/*.metainfo.xml`
- `build/`, `_prefix/`, `build-flatpak/`, `.flatpak-builder/` are throwaway; delete after use.

## Architecture

- `src/providers.py` — all network/parsing/secret logic, no GTK. A repo is identified everywhere by an identity string `host/path` (`github.com/o/r`, `gitlab.com/g/sub/p`). `parse()` turns user input into it (bare `o/r` means GitHub; GitLab only for `gitlab.com` / `gitlab.*` hosts), `migrate()` upgrades legacy bare `o/r` entries, `fetch()` dispatches on host to `_github` / `_gitlab` and returns one normalized dict (`name,url,issues,prs,ci` or `name,error`). CI vocabulary is shared: `success|failure|running|cancelled|none`; GitLab statuses are mapped in `_GL_CI`.
- API quirks that look wrong but are deliberate: GitHub `open_issues_count` includes PRs, so issues = count − PRs (PR count from the search API). GitLab project payload omits `open_issues_count` when anonymous, so issues come from `/issues_statistics`; MR count comes from the `X-Total` header.
- `src/window.py` — `Window` owns the FlowBox of `Card`s (`self.cards` keyed by identity), a refresh timer (`GLib.timeout_add_seconds`, restarted when `refresh-seconds` changes), and one daemon thread per repo per refresh; results return to the UI thread via `GLib.idle_add`. Cards removed mid-fetch are ignored in `_apply`.
- `src/prefs.py` — `Adw.PreferencesDialog`: interval + one token row per host (github.com, gitlab.com, plus any host among stored repos); tokens saved on dialog close.
- Storage: repo list and interval in GSettings (`data/io.github.vina.Painel.gschema.xml`, keys `repos`, `refresh-seconds`); tokens only in libsecret, keyed by `host` attribute (legacy `purpose=github-token` lookup kept as fallback for `github.com`). Never put tokens in GSettings/files.
- Packaging: `src/painel.in` is the launcher template; Python modules install to `<prefix>/share/painel/painel/` (not site-packages), so adding a module requires listing it in `src/meson.build`. `data/` holds desktop/metainfo/schema/icons.

## Open items before Flathub submission

App ID `io.github.vina.Painel` is a placeholder (must match a real repo/domain), plus missing screenshots, license file, and metainfo `<developer>` tag.

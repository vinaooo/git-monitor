# Painel

A GNOME dashboard for your GitHub and GitLab repositories. One card per repository shows its open issues, pending pull/merge requests, CI state and a button to open it in the browser. Built with GTK4 + libadwaita (Python/PyGObject), no third-party Python dependencies.

## Features

- **Cards** with open issues, PRs/MRs by state (waiting, ready, changes requested, failing, conflicts, drafts) and CI (passing, running, failing, cancelled). PR/MR chips link to the filtered list on the site.
- **Groups** in a sidebar: drag cards between groups, reorder, rename, pick an icon, set a refresh interval per group. Group health shows as marks and an optional tint.
- **Virtual groups**: read-only collections built from every group (GitHub, GitLab, PR/MR ready, CI failing/cancelled, PRs needing attention, waiting for review, fetch errors). They appear only while they have repositories and can be switched off in Preferences.
- **Import from account**: list a user's or organization's repositories, tick the ones you want, and optionally keep the group in sync with new repositories.
- **Search** (`Ctrl+F`) across all groups by name, URL or status words such as `waiting`, `passing`, `ready`.
- Sort and size options, a rate-limit estimate for the GitHub API, and private repositories when a token is stored in the keyring.

## Install and run

Painel is not on Flathub yet. Build and install the Flatpak from a checkout:

```
flatpak-builder --user --install --force-clean build-flatpak io.github.vina.Painel.yml
flatpak run io.github.vina.Painel
```

Requires `flatpak-builder` and the GNOME 50 runtime. From source instead (needs GTK 4, libadwaita ≥ 1.8, PyGObject, libsecret):

```
meson setup build --prefix=$PWD/_prefix && meson install -C build
GSETTINGS_SCHEMA_DIR=_prefix/share/glib-2.0/schemas XDG_DATA_DIRS=_prefix/share:/usr/share _prefix/bin/painel
```

## Access tokens

Tokens are optional. Without one, only public repositories work and the API limits are low (GitHub review states need a token). Add read-only tokens in **Preferences → Access tokens**: GitHub fine-grained (Metadata, Issues, Pull requests, Actions: read) or GitLab `read_api`, with an expiry date. They are stored in the system keyring (libsecret), never in files or settings.

## Development

```
python3 -m unittest discover -s tests -t .
```

Tests use only the standard library. `tools/headless-gnome/dnd-test.sh` runs a real drag-and-drop test in an isolated headless GNOME Shell. See [CLAUDE.md](CLAUDE.md) for the architecture notes.

## License

[MIT](LICENSE)

# Frontend review — Painel (GTK4 / libadwaita)

## Context and assumptions
- **Version target (confirmed):** Flatpak runtime GNOME 50 (libadwaita ≥ 1.9). **This does not break older GNOME hosts:** a Flatpak ships its own runtime (GTK + libadwaita), so it runs the same on any distro with Flatpak, whatever GNOME the host has. Only a non-Flatpak install (meson/deb) uses the system libadwaita; Ubuntu 24.04 has 1.5, so a deb for it would forbid `Adw.ShortcutsDialog` (1.8) and `Adw.Spinner` (1.6). The local dev box has 1.9.1.
- APIs used below: `Adw.Breakpoint` (1.4), `Adw.Dialog`/`AlertDialog` (1.5, already used), `Adw.Spinner` (1.6), `Adw.ShortcutsDialog` (1.8). All fine on runtime 50.
- **Out of scope (confirmed):** i18n/gettext, desktop notifications, .ui/Blueprint refactor, card search/filter.
- **All visual observations are inferences from code.** I did not run the app (plan mode) and have no screenshots. `[inference]` marks results I could not verify.
- Stack: Python/PyGObject, 100% imperative UI, meson + Flatpak.

## 1. Summary
**What it is:** GNOME dashboard with one card per GitHub/GitLab repo (open issues, pending PRs/MRs, CI, open in browser), organized in groups (sidebar or tabs), with sorting, card sizes, drag-and-drop, and group health tint. User: a dev watching many repos/CI at once.

**Already well done:** `Adw.ApplicationWindow` + `ToolbarView` + `OverlaySplitView`, `AlertDialog`/`PreferencesDialog`/`AboutDialog`, `ToastOverlay`, `StatusPage` for empty groups, native `TabView`/`TabBar`, model-backed `ListView` sidebar, semantic Adwaita colors, chips never rely on color alone (glyph + word), FLIP reorder animation, `UriLauncher` (portal), tokens in keyring.

**Top 5 highest-impact improvements**
1. **Keyboard/touch accessibility:** clickable chips are `Gtk.Label` + gesture (unreachable by keyboard/Orca); "Move to group" opens only on right-click.
2. **Remove is destructive and instant** (trash always visible, no undo) → toast with *Undo*.
3. **Adaptivity and window state:** no `Adw.Breakpoint` (sidebar never collapses), window size not remembered.
4. **Shortcuts and primary menu:** no accelerators at all; no shortcuts window, no Quit; menu mixes group actions with app items.
5. **Error/loading states:** an error wipes good data and shows unstyled raw text; empty group has no action button; no "Updated HH:MM".

## 2. Findings table
| ID | Area | Sev. | Effort | Location | Problem | Fix |
|---|---|---|---|---|---|---|
| F01 | E | High | S | `card.py:195-202` | Clickable chip = `Gtk.Label` + `GestureClick`: not focusable, no role; keyboard/Orca can't activate | Flat `Gtk.Button` with `chip` class when `url` is set |
| F02 | E/C | High | M | `card.py:66-85` | "Move to group" only via secondary click; no long-press (touch) or Menu/Shift+F10 key | `Gio.Menu` + `PopoverMenu` on the card; `GestureLongPress`; `card.*` actions |
| F03 | C | High | M | `card.py:32-34`, `window.py:344-349` | Always-visible trash removes immediately, loses custom title, no undo | "Removed" toast with *Undo*; trash moves into card menu |
| F04 | D | High | S | `window.py:110-111,18` | No `Adw.Breakpoint`; split view never `collapsed`; no sidebar toggle; no min width | Breakpoint `max-width: 600sp` → `collapsed`; `ToggleButton` bound to `show-sidebar` |
| F05 | C | Med | S | `window.py:18` | Window size/maximized not persisted | 3 GSettings keys + `bind` |
| F06 | A/C | Med | S | `main.py:25-31`, `window.py:49-62` | No `set_accels_for_action` (Ctrl+N, Ctrl+R/F5, Ctrl+, Ctrl+Q, Ctrl+?) | Add accelerators; `app.quit`; `Adw.ShortcutsDialog` |
| F07 | A | Med | S | `window.py:50-55`, `main.py:24-26` | Primary menu mixes group actions with Preferences/About; no Shortcuts/Quit | Sections: group / Preferences·Shortcuts / About·Quit |
| F08 | C | Med | S | `group_page.py:28-29` | Empty group: text only, no "Add Repository" button; title "Empty group" | `StatusPage` with pill suggested button → `win.add-repo` |
| F09 | C | Med | M | `card.py:178-192` | Error: only `stats.set_label(raw)`, chips cleared (`chips_for` → `[]`), no stripe/icon; last good data disappears | Keep last state + `health-error` class + `dialog-warning-symbolic` + retry |
| F10 | C | Med | S | `window.py:78`, `card.py:28` | No "Updated at…", no refresh feedback, "Loading…" without spinner | `WindowTitle` subtitle; `Adw.Spinner` in refresh button while pending |
| F11 | C | Med | S | `window.py:316-337` | Invalid input closes dialog and shows toast; user retypes everything | Enable "Add" only when `repo_id.parse` succeeds; keep dialog open |
| F12 | E | Med | M | `window.py:145`, `style.py:10-17` | Group health shown by color only (tint), contradicting the project's own rule | Icon on sidebar row (`dialog-error-symbolic`, …) besides the tint |
| F13 | F | Med | M | `window.py:392-414` | One thread per repo per cycle, no cap or in-flight guard; each result calls `_apply_sort` + `_update_marks` (walks the whole TabBar tree) → O(N²) | `ThreadPoolExecutor(4)` + in-flight set; coalesce marks in one `idle_add` |
| F14 | C | Med | S | `card.py:103-138`, `window.py:289` | Rename only on hover (no touch); group rename only via menu, no context menu on tab/row | Reuse F02 menu with *Rename*; context menu on sidebar row/tab |
| F15 | G | Med | S | `data/*.metainfo.xml`, `main.py:41-43`, `.desktop` | Metainfo lacks `<developer>`, screenshots, `<branding>`, `<requires>` display length, bugtracker; homepage `github.com/vina/painel` likely wrong (PRs come from `vinaooo/…`) [verify]; About says "Monitor GitHub repositories" (omits GitLab), no `developer_name`/`website`/`issue_url`; `.desktop` has no `Keywords` | Complete them |
| F16 | B | Low | S | `card.py:190` | "1 open issues" | Simple conditional (no gettext) |
| F17 | B | Low | S | `style.py:7,22,10-17` | Fixed `@blue_2/@blue_3` and `mix(…, white, …)` assume a light theme; `.chip.warning` contrast on light bg [inference, measure] | Check contrast in both schemes; keep fixed blue (documented: accent may be gray) |
| F18 | B | Low | S | `window.py:88` | `view-grid-symbolic` fixed even in list mode | Swap icon by `view` |
| F19 | B | Low | S | `group_page.py:30-31` | `Stack` has no transition empty↔list | `transition_type=CROSSFADE` |
| F20 | C | Low | S | `card.py:30-33` | Two always-visible buttons per card = noise; card itself not activatable | Activatable card + `⋮` menu (with F03), or move trash into menu |
| F21 | E | Low | S | `window.py:71,80-83,103`, `card.py:104` | Icon-only buttons rely on tooltip for accessible name [inference: check with Accerciser/Orca] | `update_property([Gtk.AccessibleProperty.LABEL], […])` |
| F22 | F | Nice | S | `window.py:41-46` | `settings.connect` never disconnected (single window → harmless) | Ignore |

Not recommended: replacing the card `FlowBox` with `GridView`. Live drag preview, FLIP and slots depend on it (CLAUDE.md), and card counts are small.

## 3. Detailed recommendations (High/Medium)

**F01 — accessible chip** (`card.py:_chip_label`)
```python
# before
label = Gtk.Label(label=chip.text, css_classes=['chip', chip.css], tooltip_text=chip.tooltip or None)
if chip.url: ...GestureClick + set_cursor...
# after
if chip.url:
    w = Gtk.Button(label=chip.text, css_classes=['flat', 'chip', 'chip-link', chip.css],
                   tooltip_text=(chip.tooltip + '\n\n' if chip.tooltip else '') + 'Open in browser')
    w.connect('clicked', lambda *_: self._launch(chip.url))
    return w
return Gtk.Label(label=chip.text, css_classes=['chip', chip.css], tooltip_text=chip.tooltip or None)
```
CSS: `button.chip { min-height: 0; min-width: 0; }`. Pointer cursor comes for free.

**F02/F14 — one context menu for the card**
```python
menu = Gio.Menu(); menu.append('Rename…', 'card.rename'); menu.append('Open in browser', 'card.open')
moves = Gio.Menu()
for g in other_groups(self.ident): moves.append(g, f'card.move::{g}')   # string-parameter action
menu.append_submenu('Move to group', moves); menu.append('Remove', 'card.remove')
self.pop = Gtk.PopoverMenu.new_from_model(menu); self.pop.set_parent(self)
for gesture in (Gtk.GestureClick(button=Gdk.BUTTON_SECONDARY), Gtk.GestureLongPress()):
    gesture.connect('pressed', lambda g, *a: self._open_menu(*a[-2:])); self.add_controller(gesture)
```
Build the submenu inside `_open_menu` (groups change). Add an `EventControllerKey` for `Gdk.KEY_Menu`/Shift+F10. Unparent the popover on dispose.

**F03 — remove with Undo** (`window.py:remove_repo`)
```python
def remove_repo(self, name):
    group, title = self.groups.group_of(name), self.titles.get(name)
    self._drop_repo(name)                      # today's remove_repo body
    toast = Adw.Toast(title=f'Removed {name.rpartition("/")[2]}', button_label='Undo', timeout=8)
    toast.connect('button-clicked', lambda *_: self._restore(name, group, title))
    self.toasts.add_toast(toast)
```
`_restore` = `groups.add_repo` + `titles.set` + `_add_card` + `refresh`. Original position is lost (appended); acceptable.

**F04 — breakpoint** (`window._build_ui`, after `self.split`)
```python
self.set_size_request(360, 294)
bp = Adw.Breakpoint.new(Adw.BreakpointCondition.parse('max-width: 600sp'))
bp.add_setter(self.split, 'collapsed', True)
self.add_breakpoint(bp)
toggle = Gtk.ToggleButton(icon_name='sidebar-show-symbolic', tooltip_text='Groups')
toggle.bind_property('active', self.split, 'show-sidebar', GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE)
content_header.pack_start(toggle)   # visible only when collapsed and layout == sidebar
```
`_apply_layout` currently does `set_show_sidebar(sidebar)`; in tabs layout the sidebar must stay hidden and the toggle invisible. When collapsed, selecting a group should close the overlay.

**F05 — window state**
```xml
<key name="window-width" type="i"><default>900</default></key>
<key name="window-height" type="i"><default>600</default></key>
<key name="window-maximized" type="b"><default>false</default></key>
```
```python
settings.bind('window-width', self, 'default-width', Gio.SettingsBindFlags.DEFAULT)
settings.bind('window-height', self, 'default-height', Gio.SettingsBindFlags.DEFAULT)
settings.bind('window-maximized', self, 'maximized', Gio.SettingsBindFlags.DEFAULT)
```

**F06/F07 — shortcuts + menu**
```python
app.set_accels_for_action('win.new-group', ['<Ctrl>n'])
app.set_accels_for_action('win.add-repo', ['<Ctrl>t'])
app.set_accels_for_action('win.refresh', ['<Ctrl>r', 'F5'])
app.set_accels_for_action('app.prefs', ['<Ctrl>comma'])
app.set_accels_for_action('app.shortcuts', ['<Ctrl>question'])
app.set_accels_for_action('app.quit', ['<Ctrl>q'])
```
Turn the header "Add"/"Refresh" buttons into `win.add-repo`/`win.refresh` actions (today bare `clicked` handlers). Menu: `[New/Rename/Delete group]`, `[Preferences, Keyboard Shortcuts]`, `[About Painel, Quit]`. Shortcuts: `Adw.ShortcutsDialog` with `Adw.ShortcutsSection`/`Adw.ShortcutsItem`.

**F08 — empty state with action**
```python
btn = Gtk.Button(label='Add Repository', halign=Gtk.Align.CENTER, css_classes=['suggested-action', 'pill'], action_name='win.add-repo')
Adw.StatusPage(title='No Repositories', icon_name=…, description='Add a repository, or drag a card onto this group.', child=btn)
```

**F09/F10 — error and loading**
- `Card.update`: if `s.error` and a good `self.status` exists, don't call `_set_chips([])`; add `health-error`, show "Couldn't refresh · <error>" with `dialog-warning-symbolic` and `.error` class, dim old chips.
- `Window.refresh`: refresh button swaps to `Adw.Spinner` until the last pending `_apply`; `window_title.set_subtitle(f'Updated {time}')` in `_apply`.

**F11 — inline validation** (`ask_repo`): `dlg.set_response_enabled('add', False)` and `entry.connect('changed', lambda e: dlg.set_response_enabled('add', bool(repo_id.parse(e.get_text()))))`. Drop the "Invalid repository" toast.

**F12 — health without color:** in the sidebar `bind`, add a trailing `Gtk.Image` with icon by severity, updated on the same `notify::keyword`, with an accessible description. Tabs already carry `● N` in the title.

**F13 — controlled refresh** (`window.py`)
```python
self.pool, self.inflight = ThreadPoolExecutor(max_workers=4), set()
def refresh(self):
    ...
    for name in names:
        if name in self.inflight: continue
        self.inflight.add(name); self.pool.submit(self._worker, name, token_for(name))
def _worker(self, name, token):
    GLib.idle_add(self._apply, name, self.service.fetch(name, token))
def _apply(self, name, data):
    self.inflight.discard(name); ...
    self._marks_dirty or GLib.idle_add(self._flush_marks)   # coalesce _update_marks/_tint_tabs
```

**F15 — packaging:** metainfo `<developer id="…"><name>…</name></developer>`, `<screenshots>`, `<branding>`, `<requires><display_length compare="ge">360</display_length></requires>`, `<url type="bugtracker">`, fix homepage. `.desktop`: `Keywords=github;gitlab;ci;issues;pull requests;merge requests;`. About: `developer_name`, `website`, `issue_url`, `comments='Monitor GitHub and GitLab repositories'`. Overlaps CLAUDE.md "Open items" (placeholder ID, screenshots).

## 4. Quick wins (< 30 min each)
- [ ] F16 plural "1 open issue"
- [ ] F19 crossfade on group `Stack`
- [ ] F18 view-menu icon per mode
- [ ] F08 empty-state button
- [ ] F06 accelerators + `app.quit`
- [ ] F05 persist window state
- [ ] F11 enable "Add" only for valid input
- [ ] F15 About text + `Keywords` + homepage
- [ ] F01 chips as buttons
- [ ] F10 "Updated HH:MM" subtitle

## 5. Bigger ideas
- **Sidebar rows with health icon + ready-PR badge** (extends F12): replaces the `● N` title hack, better for Orca. Trade-off: rewrite the sidebar `bind`.
- **`Adw.ActionRow`-based List view:** native keyboard/Orca behavior; cost: a second UI path next to the compact `Card`.
- **"Failures only" quick filter** (health filter, not search): toggle in the view menu using `sorting.py`/`health.severity`. Cheap, useful for a dashboard.

## 6. Roadmap (each step = its own commit)
| # | Step | Files |
|---|---|---|
| 1 | Visual quick wins: F16, F18, F19, F08 | `card.py`, `group_page.py`, `window.py` |
| 2 | Accessible chips (F01) | `card.py`, `style.py` |
| 3 | Window: persisted size + breakpoint + sidebar toggle (F04, F05) | `window.py`, `data/*.gschema.xml` |
| 4 | Actions, shortcuts, primary menu, Shortcuts dialog (F06, F07) | `main.py`, `window.py` |
| 5 | Card/group context menu + long-press (F02, F14) | `card.py`, `window.py` |
| 6 | Remove with Undo (F03, F20) | `card.py`, `window.py` |
| 7 | Add-repo inline validation (F11) | `window.py` |
| 8 | Error/loading states + "Updated" (F09, F10) | `card.py`, `window.py`, `style.py` |
| 9 | Group health without color (F12) | `window.py`, `style.py` |
| 10 | Pooled refresh + coalesced marks (F13) | `window.py` |
| 11 | Metainfo/About/.desktop (F15) | `data/*`, `main.py` |

After approval: save this plan as `UI_REVIEW.md` at the project root, then implement step 1 and stop for your OK before each next step.

## Verification (per step)
- `python3 -m unittest discover -s tests -t .` (add a stdlib test when logic is pure)
- Run from prefix: `meson setup build --prefix=$PWD/_prefix && meson install -C build`, then `GSETTINGS_SCHEMA_DIR=_prefix/share/glib-2.0/schemas XDG_DATA_DIRS=_prefix/share:/usr/share _prefix/bin/painel`
- Steps 3/4: resize to ~400 px, check collapsed sidebar and shortcuts; reopen and confirm restored size.
- Steps 2/5: drive it with Tab/Enter/Menu key only (and Orca if available).
- Steps 5/6: `tools/headless-gnome/dnd-test.sh` must print `RESULT OK`.
- Step 11: `desktop-file-validate data/*.desktop` and `appstreamcli validate --no-net data/*.metainfo.xml`.
- Delete `build/` and `_prefix/` afterwards.

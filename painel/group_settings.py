from gi.repository import Adw, Gtk

from .icon_picker import IconPicker


class GroupSettingsDialog(Adw.Dialog):
    """Per-group settings (for now the refresh interval). `on_save(seconds | None)` runs when the dialog closes
    with a changed value. `account` (+ `on_browse`) is set for a group imported from an account: a row lists all of its
    repositories to add more."""

    def __init__(self, group, rows, current, on_save, account=None, on_browse=None, icon=None, on_icon=None,
                 notify=True, on_notify=None):
        super().__init__(title=f'{group} settings', content_width=440)
        self.rows, self.current, self.on_save = rows, current, on_save
        self.icon, self.on_icon, self.picker = icon, on_icon, IconPicker(icon)
        self.notify, self.on_notify = notify, on_notify
        page = Adw.PreferencesPage()
        looks = Adw.PreferencesGroup(title='Icon')
        looks.add(self.picker)
        page.add(looks)
        box = Adw.PreferencesGroup(title='Refresh')
        for row in rows.rows:
            box.add(row)
        page.add(box)
        alerts = Adw.PreferencesGroup(title='Notifications')
        self.notify_row = Adw.SwitchRow(title='Notify on CI changes', active=notify)
        alerts.add(self.notify_row)
        page.add(alerts)
        if account:
            repos = Adw.PreferencesGroup(title='Repositories')
            row = Adw.ActionRow(title='Add repositories from this account', subtitle=account, activatable=True)
            row.add_suffix(Gtk.Image.new_from_icon_name('go-next-symbolic'))
            row.connect('activated', lambda *_: (self.close(), on_browse()))
            repos.add(row)
            page.add(repos)
        view = Adw.ToolbarView(content=page)
        view.add_top_bar(Adw.HeaderBar())
        self.set_child(view)
        self.connect('closed', lambda *_: self._save())

    def _save(self):
        if self.picker.value() != self.icon:
            self.on_icon(self.picker.value())
        if self.notify_row.get_active() != self.notify:
            self.on_notify(self.notify_row.get_active())
        value = self.rows.value()
        if value != self.current:
            self.on_save(value)

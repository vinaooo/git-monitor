from gi.repository import Adw, Gtk


class GroupSettingsDialog(Adw.Dialog):
    """Per-group settings (for now the refresh interval). `on_save(seconds | None)` runs when the dialog closes
    with a changed value."""

    def __init__(self, group, rows, current, on_save):
        super().__init__(title=f'{group} settings', content_width=440)
        self.rows, self.current, self.on_save = rows, current, on_save
        page = Adw.PreferencesPage()
        box = Adw.PreferencesGroup(title='Refresh')
        for row in rows.rows:
            box.add(row)
        page.add(box)
        view = Adw.ToolbarView(content=page)
        view.add_top_bar(Adw.HeaderBar())
        self.set_child(view)
        self.connect('closed', lambda *_: self._save())

    def _save(self):
        value = self.rows.value()
        if value != self.current:
            self.on_save(value)

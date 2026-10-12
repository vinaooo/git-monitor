from gi.repository import Gtk

from .icons import CHOICES


class IconPicker(Gtk.FlowBox):
    """Grid of icons to choose a group's icon from. `value()` is the chosen icon name."""

    def __init__(self, selected):
        super().__init__(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True, min_children_per_line=5,
                         max_children_per_line=10, row_spacing=4, column_spacing=4)
        self.selected, first = selected, None
        for name in CHOICES:
            button = Gtk.ToggleButton(icon_name=name, tooltip_text=name.removeprefix('painel-').removesuffix('-symbolic').replace('-', ' '),
                                      css_classes=['flat'], active=name == selected)
            button.update_property([Gtk.AccessibleProperty.LABEL], [button.get_tooltip_text()])
            if first:
                button.set_group(first)
            first = first or button
            button.connect('toggled', self._toggled, name)
            self.append(button)

    def _toggled(self, button, name):
        if button.get_active():
            self.selected = name

    def value(self):
        return self.selected

from gi.repository import Gdk, Gtk

# Semantic Adwaita colors, so accent/dark mode and the user's own gtk.css (applied at USER priority) still win.
CSS = """
.card.health-error   { box-shadow: inset 4px 0 0 @error_color,   0 0 0 1px alpha(currentColor, .1); }
.card.health-warning { box-shadow: inset 4px 0 0 @warning_color, 0 0 0 1px alpha(currentColor, .1); }
.card.health-accent  { box-shadow: inset 4px 0 0 @blue_3, 0 0 0 1px alpha(currentColor, .1); }
.card.health-success { box-shadow: inset 4px 0 0 @success_color, 0 0 0 1px alpha(currentColor, .1); }
.chip { padding: 1px 9px; border-radius: 99px; font-size: smaller; font-weight: 600; }
.chip.error      { color: @error_color;   background: alpha(@error_color, .15); }
.chip.warning    { color: @warning_color; background: alpha(@warning_color, .15); }
.chip.accent     { color: @blue_2;        background: alpha(@blue_3, .22); }  /* fixed blue: the user's accent may be gray/green */
.chip.success    { color: @success_color; background: alpha(@success_color, .15); }
.chip.dim-label  { background: alpha(currentColor, .08); }
"""


def install():
    provider = Gtk.CssProvider()
    provider.load_from_string(CSS)
    Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider,
                                              Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

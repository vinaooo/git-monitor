from gi.repository import Gdk, Gtk

# Semantic Adwaita colors, so accent/dark mode and the user's own gtk.css (applied at USER priority) still win.
CSS = """
.card.health-error   { box-shadow: inset 4px 0 0 @error_color,   0 0 0 1px alpha(currentColor, .1); }
.card.health-warning { box-shadow: inset 4px 0 0 @warning_color, 0 0 0 1px alpha(currentColor, .1); }
.card.health-accent  { box-shadow: inset 4px 0 0 @blue_3, 0 0 0 1px alpha(currentColor, .1); }
.card.health-success { box-shadow: inset 4px 0 0 @success_color, 0 0 0 1px alpha(currentColor, .1); }
window .card.search-hit { background-color: mix(@accent_bg_color, @card_bg_color, .65); background-image: none; box-shadow: 0 0 0 3px @accent_bg_color; }
/* group health tint (only with the colored-tabs preference, i.e. "Colored group rows"): whole sidebar row, a light (white-mixed) translucent wash so the theme still shows through */
window.colored-tabs row.tint-error       { background: alpha(mix(@error_color, white, .4), .30); }
window.colored-tabs row.tint-warning   { background: alpha(mix(@warning_color, white, .4), .30); }
window.colored-tabs row.tint-accent     { background: alpha(mix(@blue_3, white, .4), .32); }
window.colored-tabs row.tint-success   { background: alpha(mix(@success_color, white, .4), .26); }
window.colored-tabs row.tint-error:selected       { background: alpha(mix(@error_color, white, .4), .50); }
window.colored-tabs row.tint-warning:selected   { background: alpha(mix(@warning_color, white, .4), .50); }
window.colored-tabs row.tint-accent:selected     { background: alpha(mix(@blue_3, white, .4), .52); }
window.colored-tabs row.tint-success:selected   { background: alpha(mix(@success_color, white, .4), .44); }
listview.dim-selection row:selected { background: none; }
.sidebar-group { padding: 10px 12px; }
/* dragging a group: every row becomes a tile that moves with its content; the row's own wash would stay behind */
listview.reordering row, listview.reordering row:hover, listview.reordering row:selected,
window.colored-tabs listview.reordering row, window.colored-tabs listview.reordering row:selected { background: none; }
.sidebar-group.reorder-tile { border-radius: 8px; background: alpha(currentColor, .05); box-shadow: inset 0 0 0 1px alpha(currentColor, .15); }
.sidebar-group.reorder-gap { background: alpha(@accent_bg_color, .12); box-shadow: none; border: 2px dashed alpha(@accent_bg_color, .6); padding: 8px 10px; }
.sidebar-group.reorder-gap > * { opacity: 0; }
window.colored-icons .mark-error   { color: @error_color; }
window.colored-icons .mark-warning { color: @warning_color; }
window.colored-icons .mark-accent  { color: @blue_3; }
window.colored-icons .mark-success { color: @success_color; }
.chip { padding: 1px 9px; border-radius: 99px; font-size: smaller; font-weight: 600; }
button.chip { min-height: 0; min-width: 0; }
.chip-link:hover { filter: brightness(1.25); }
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

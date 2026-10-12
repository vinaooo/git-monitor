"""GNOME Shell search provider (org.gnome.Shell.SearchProvider2): the Shell search lists matching cards, e.g. "painel failing"."""
from gi.repository import Gio, GLib

from .search import matches

PATH = '/io/github/vina/Painel/SearchProvider'
LIMIT = 20
XML = """<node><interface name="org.gnome.Shell.SearchProvider2">
<method name="GetInitialResultSet"><arg type="as" name="terms" direction="in"/><arg type="as" name="results" direction="out"/></method>
<method name="GetSubsequentResultSet"><arg type="as" name="previous" direction="in"/><arg type="as" name="terms" direction="in"/><arg type="as" name="results" direction="out"/></method>
<method name="GetResultMetas"><arg type="as" name="identifiers" direction="in"/><arg type="aa{sv}" name="metas" direction="out"/></method>
<method name="ActivateResult"><arg type="s" name="identifier" direction="in"/><arg type="as" name="terms" direction="in"/><arg type="u" name="timestamp" direction="in"/></method>
<method name="LaunchSearch"><arg type="as" name="terms" direction="in"/><arg type="u" name="timestamp" direction="in"/></method>
</interface></node>"""


def find(terms, items):
    """Idents of `items` ((ident, title, status)) matching every term; a leading "painel" only names the app."""
    words = [t for t in terms if t.lower() != 'painel']
    query = ' '.join(words)
    return [i for i, title, status in items if matches(query, i, title, status)][:LIMIT]


def register(app, connection, items):
    """Export the provider on `connection`; `items()` returns the current (ident, title, status) list."""
    def call(_conn, _sender, _path, _iface, method, params, invocation):
        args = params.unpack()
        if method == 'GetInitialResultSet':
            invocation.return_value(GLib.Variant('(as)', (find(args[0], items()),)))
        elif method == 'GetSubsequentResultSet':
            invocation.return_value(GLib.Variant('(as)', (find(args[1], items()),)))
        elif method == 'GetResultMetas':
            known = {i: (t, s) for i, t, s in items()}
            metas = [{'id': GLib.Variant('s', i), 'name': GLib.Variant('s', known[i][0]),
                      'description': GLib.Variant('s', (known[i][1] and known[i][1].url) or i),
                      'gicon': GLib.Variant('s', app.get_application_id())} for i in args[0] if i in known]
            invocation.return_value(GLib.Variant('(aa{sv})', (metas,)))
        else:
            app.activate_action('open-card', GLib.Variant('s', args[0])) if method == 'ActivateResult' else app.activate()
            invocation.return_value(None)

    return connection.register_object(PATH, Gio.DBusNodeInfo.new_for_xml(XML).interfaces[0], call, None, None)

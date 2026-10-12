"""Background portal: lets the app keep running (and autostart) with its window closed. No GTK; stdlib + Gio only."""
import logging

from gi.repository import Gio, GLib

log = logging.getLogger(__name__)


def options(autostart, commandline=('painel',)):
    """`a{sv}` options of org.freedesktop.portal.Background.RequestBackground."""
    return {'reason': GLib.Variant('s', 'Keep checking repositories and send CI notifications'),
            'autostart': GLib.Variant('b', autostart),
            'commandline': GLib.Variant('as', list(commandline)),
            'dbus-activatable': GLib.Variant('b', False)}


def request(autostart):
    """Ask the portal (async, errors only logged: it fails outside a sandbox and the user may deny it)."""
    def done(proxy, result):
        try:
            proxy.call_finish(result)
        except GLib.Error as e:
            log.warning('background portal: %s', e.message)

    try:
        proxy = Gio.DBusProxy.new_for_bus_sync(
            Gio.BusType.SESSION, Gio.DBusProxyFlags.NONE, None, 'org.freedesktop.portal.Desktop',
            '/org/freedesktop/portal/desktop', 'org.freedesktop.portal.Background', None)
        proxy.call('RequestBackground', GLib.Variant('(sa{sv})', ('', options(autostart))),
                   Gio.DBusCallFlags.NONE, -1, None, done)
    except GLib.Error as e:
        log.warning('background portal: %s', e.message)

"""Group icons: the list offered when creating a group, and the per-group choice. Pure; names are Adwaita symbolic icons."""

DEFAULT = 'folder-symbolic'
CHOICES = (
    'folder-symbolic', 'go-home-symbolic', 'starred-symbolic', 'user-bookmarks-symbolic', 'view-pin-symbolic',
    'computer-symbolic', 'network-server-symbolic', 'utilities-terminal-symbolic', 'applications-engineering-symbolic',
    'applications-science-symbolic', 'applications-games-symbolic', 'applications-graphics-symbolic',
    'applications-multimedia-symbolic', 'applications-utilities-symbolic', 'system-run-symbolic',
    'preferences-system-symbolic', 'security-high-symbolic', 'package-x-generic-symbolic', 'text-x-generic-symbolic',
    'chat-message-new-symbolic', 'mail-unread-symbolic', 'camera-photo-symbolic', 'emoji-nature-symbolic',
    'emoji-travel-symbolic', 'emoji-objects-symbolic', 'weather-clear-symbolic', 'alarm-symbolic',
    'find-location-symbolic', 'input-gaming-symbolic', 'bookmark-new-symbolic',
    'painel-github-symbolic', 'painel-gitlab-symbolic', 'painel-forgejo-symbolic',  # the app's own (data/*.svg)
)


class IconStore:
    """Icon name per group; a group without one gets DEFAULT. Persistence is injected via `save({group: icon})`,
    like `IntervalStore`."""

    def __init__(self, icons, save):
        self._icons, self._save = dict(icons), save

    def get(self, group):
        return self._icons.get(group, DEFAULT)

    def set(self, group, icon):
        if icon == DEFAULT:
            self._icons.pop(group, None)
        else:
            self._icons[group] = icon
        self._save(dict(self._icons))

    def rename_group(self, old, new):
        if old in self._icons:
            self._icons[new] = self._icons.pop(old)
            self._save(dict(self._icons))

    def remove_group(self, group):
        if self._icons.pop(group, None) is not None:
            self._save(dict(self._icons))

install_data(app_id + '.desktop', install_dir: get_option('datadir') / 'applications')
install_data(app_id + '.metainfo.xml', install_dir: get_option('datadir') / 'metainfo')
install_data(app_id + '.gschema.xml', install_dir: get_option('datadir') / 'glib-2.0' / 'schemas')
install_data(app_id + '.svg', install_dir: get_option('datadir') / 'icons/hicolor/scalable/apps')
install_data(app_id + '-symbolic.svg', 'painel-github-symbolic.svg', 'painel-gitlab-symbolic.svg', 'painel-forgejo-symbolic.svg',
             install_dir: get_option('datadir') / 'icons/hicolor/symbolic/apps')
install_data(app_id + '.search-provider.ini', install_dir: get_option('datadir') / 'gnome-shell' / 'search-providers')
configure_file(input: app_id + '.service.in', output: app_id + '.service', install: true,
               install_dir: get_option('datadir') / 'dbus-1' / 'services',
               configuration: {'app_id': app_id, 'bindir': get_option('prefix') / get_option('bindir')})

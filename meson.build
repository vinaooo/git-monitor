project('painel', version: '0.1.0', meson_version: '>= 1.0')

gnome = import('gnome')
python = import('python')
py = python.find_installation('python3')

app_id = 'io.github.vina.Painel'
pkgdatadir = get_option('prefix') / get_option('datadir') / meson.project_name()

subdir('data')
subdir('src')
subdir('painel')
gnome.post_install(glib_compile_schemas: true, gtk_update_icon_cache: true, update_desktop_database: true)

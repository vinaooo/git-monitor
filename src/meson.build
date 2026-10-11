conf = configuration_data()
conf.set('PYTHON', py.full_path())
conf.set('PKGDATADIR', pkgdatadir)
configure_file(input: 'painel.in', output: 'painel', configuration: conf, install: true, install_dir: get_option('bindir'), install_mode: 'rwxr-xr-x')

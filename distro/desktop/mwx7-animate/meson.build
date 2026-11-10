# MWX 7 window animations: a fork of Wayfire 0.9's animate plugin (MIT, see LICENSE.wayfire) without the fire effect
# and with the MWX 7 genie for minimize / restore. Reads the same [animate] options; load it as "mwx7-animate"
# instead of "animate". Adds the IPC method mwx7/set-minimize-hint so the dock can say where a window's icon is.
project('mwx7-animate', 'cpp', version: '0.1', default_options: ['cpp_std=c++17', 'buildtype=release', 'warning_level=1'])
wayfire = dependency('wayfire')
deps = [wayfire, dependency('wf-config'), dependency('wlroots-0.18'), dependency('pixman-1'), dependency('glm'),
        dependency('nlohmann_json')]
shared_module('mwx7-animate', ['animate.cpp'],
  dependencies: deps,
  cpp_args: ['-DWLR_USE_UNSTABLE', '-DWAYFIRE_PLUGIN'],
  install: true,
  install_dir: wayfire.get_variable(pkgconfig: 'plugindir'))
install_data('mwx7-animate.xml', install_dir: wayfire.get_variable(pkgconfig: 'metadatadir'))

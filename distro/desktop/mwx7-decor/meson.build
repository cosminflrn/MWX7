# MWX 7 window frames: a fork of Wayfire 0.9's decoration plugin (MIT, see LICENSE.wayfire) with MWX 7's glass,
# caption glow and glossy traffic lights. Reads the same [decoration] options; load it as "mwx7-decor".
project('mwx7-decor', 'cpp', version: '0.1', default_options: ['cpp_std=c++17', 'buildtype=release', 'warning_level=1'])
wayfire = dependency('wayfire')
wfconfig = dependency('wf-config')
wlroots = dependency('wlroots-0.18')
deps = [wayfire, wfconfig, wlroots, dependency('pixman-1'), dependency('cairo'), dependency('pango'),
        dependency('pangocairo'), dependency('glm')]
shared_module('mwx7-decor',
  ['decoration.cpp', 'deco-subsurface.cpp', 'deco-button.cpp', 'deco-layout.cpp', 'deco-theme.cpp'],
  dependencies: deps,
  cpp_args: ['-DWLR_USE_UNSTABLE', '-DWAYFIRE_PLUGIN'],
  install: true,
  install_dir: wayfire.get_variable(pkgconfig: 'plugindir'))

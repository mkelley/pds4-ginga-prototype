"""
You need a setup function for each plugin that you are registering.
In this example we register two plugins: one global, one local

To register your plugin, you are going to create a plugin "spec"
(specification).  The format is the same but the content is slightly
different depending on whether you are registering a global plugin
(the most general kind) or a local plugin (which you can open
multiple instances--one per Ginga channel).

--------

Components of a global plugin spec:
    path: str
        the path to the plugin file itself
    module: str
        the python name of the plugin module
    klass: str
        the name of the class inside the module implementing the plugin
    tab: str
        the name the plugin should be shown as in e.g. a title bar or tab
    workspace: str
        the name of the workspace that the plugin should open in
    start: bool
        True if the plugin should be launched at program startup time


--------
Components of a local plugin spec:
    path: str
        the path to the plugin file itself
    module: str
        the python name of the plugin module
    klass: str
        the name of the class inside the module implementing the plugin
    workspace: str
        the name of the workspace that the plugin should open in

"""
from ginga.misc.Bunch import Bunch

import os.path
# my plugins are available here
p_path = os.path.split(__file__)[0]

def setup_pds4browser_global():
    spec = Bunch(path=os.path.join(p_path, 'PDS4Browser.py'),
                 module='PDS4Browser', klass='PDS4Browser',
                 tab='Open File', workspace='right', start=False,
                 category='Global')
    return spec

def setup_pds4browser_local():
    spec = Bunch(module='PDS4Browser', workspace='dialogs',
                 klass='PDS4Browser', category=None)
    return spec

# END

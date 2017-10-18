# This is open-source software licensed under a BSD license.
# Please see the file LICENSE.txt for details.
"""
A plugin for browsing the local filesystem and loading files.

**Plugin Type: Global or Local**

``FBrowser`` is a hybrid global/local plugin, which means it can be invoked
in either fashion.  If invoked as a local plugin then it is associated
with a channel, and an instance can be opened for each channel.  It can
also be opened as a global plugin.

**Usage**

Navigate the directory tree until you come to the location files
you want to load.  You can double click a file to load it into the
associated channel, or drag a file into a channel viewer window to
load it into any channel viewer.

Multiple files can be selected by holding down ``Ctrl`` (``Command`` on Mac),
or ``Shift``-clicking to select a contiguous range of files.

You may also enter full path to the desired image(s) in the text box as
``/my/path/to/image.fits``, ``/my/path/to/image.fits[ext]``,
``/my/path/to/image*.fits``, or ``/my/path/to/image*.fits[ext]``.

Because it is a local plugin, ``FBrowser`` will remember its last
directory if closed and then restarted.

"""
import glob
import os
import time

from ginga.misc import Bunch
from ginga import GingaPlugin
from ginga.util import paths, iohelper
from ginga.util.six.moves import map
from ginga.gw import Widgets

__all__ = ['PDS4Browser']

class InvalidPDS4Data(Exception):
    pass

class PDS4LabelHandler(object):
    def __init__(self, logger):
        self.logger = logger
        self.factory_dict = {}

    def register_type(self, name, klass):
        self.factory_dict[name.lower()] = klass

    def load_file(self, filespec, numhdu=None, dstobj=None, **kwdargs):
        # create object of the appropriate type, usually
        # an AstroImage or AstroTable, by looking up the correct
        # class in self.factory_dict, under the keys 'image' or
        # 'table'
        import numpy as np
        from urllib.parse import urlparse
        #from urllib.request import urlopen
        from pds4_tools import pds4_read

        urlinfo = urlparse(filespec)
        if urlinfo.scheme not in ['file', '']:
            raise IOError('File must be local: {}'.format(filespec))
        
        struct = pds4_read(urlinfo.path)

        if numhdu is None:
            # return the first table or array
            for i in range(len(struct)):
                if struct[i].is_array():
                    break
            else:
                raise InvalidPDS4Data('No image found in {}'.format(filespec))
        else:
            i = numhdu

        im = np.array(struct[i].data)

        # Ginga draws from bottom to top, left to right.  Transform
        # our data so that when it is drawn this way it is displayed
        # in the correct orientation
        disp_dir = struct[i].meta_data.display_settings['Display_Direction']
        haxis = struct[i].meta_data.get_axis_array(
            disp_dir['horizontal_display_axis']
        )
        
        # PDS4 data is Last Index Fastest and axis numbering starts at
        # 1.  Numpy arrays are also Last Index Fastest, but start at
        # 0.
        if haxis['sequence_number'] == 1:
            # Swap axes so that the horizontal axis is numpy axis 1:
            im = im.T

        hdisp_dir = disp_dir['horizontal_display_direction']
        vdisp_dir = disp_dir['vertical_display_direction']
        if 'Right to Left' in hdisp_dir:
            im = im[:, ::-1]  # invert horizontal axis
        if 'Top to Bottom' in vdisp_dir:
            im = im[::-1]     # invert vertical axis
        
        if dstobj is not None:
            dstobj.set_data(im)
        
        return im, i, None

class PDS4Browser(GingaPlugin.LocalPlugin):

    def __init__(self, *args):
        # superclass defines some variables for us, like logger
        if len(args) == 2:
            super(PDS4Browser, self).__init__(*args)
        else:
            super(PDS4Browser, self).__init__(args[0], None)

        keywords = [('Object', 'OBJECT'),
                    ('Date', 'DATE-OBS'),
                    ('Time UT', 'UT')]
        columns = [('Type', 'icon'),
                   ('Name', 'name'),
                   ('Size', 'st_size_str'),
                   ('Mode', 'st_mode_oct'),
                   ('Last Changed', 'st_mtime_str')]

        self.jumpinfo = []

        # setup plugin preferences
        prefs = self.fv.get_preferences()
        self.settings = prefs.create_category('plugin_PDS4Browser')
        self.settings.add_defaults(home_path=paths.home,
                                   keywords=keywords,
                                   columns=columns,
                                   color_alternate_rows=True,
                                   max_rows_for_col_resize=5000)
        self.settings.load(onError='silent')

        homedir = self.settings.get('home_path', None)
        if homedir is None or not os.path.isdir(homedir):
            homedir = paths.home
        self.curpath = os.path.join(homedir, '*')
        self.keywords = self.settings.get('keywords', keywords)
        self.columns = self.settings.get('columns', columns)
        self.moving_cursor = False
        self.na_dict = {attrname: 'N/A' for colname, attrname in self.columns}

        # Make icons
        icondir = self.fv.iconpath
        self.folderpb = self.fv.get_icon(icondir, 'folder.png')
        self.filepb = self.fv.get_icon(icondir, 'file.png')
        self.imagepb = self.fv.get_icon(icondir, 'fits.png')

    def build_gui(self, container):

        vbox = Widgets.VBox()
        vbox.set_margins(2, 2, 2, 2)

        # create the table
        color_alternate = self.settings.get('color_alternate_rows', True)
        table = Widgets.TreeView(sortable=True, selection='multiple',
                                 use_alt_row_color=color_alternate,
                                 dragable=True)
        table.add_callback('activated', self.item_dblclicked_cb)
        table.add_callback('drag-start', self.item_drag_cb)

        # set header
        col = 0
        self._name_idx = 0
        for hdr, attrname in self.columns:
            if attrname == 'name':
                self._name_idx = col
            col += 1
        table.setup_table(self.columns, 1, 'name')

        vbox.add_widget(table, stretch=1)
        self.treeview = table

        self.entry = Widgets.TextEntry()
        vbox.add_widget(self.entry, stretch=0)
        self.entry.add_callback('activated', self.browse_cb)

        btns = Widgets.HBox()
        btns.set_spacing(3)

        btn = Widgets.Button("Close")
        btn.add_callback('activated', lambda w: self.close())
        btn.set_tooltip("Close this plugin")
        btns.add_widget(btn, stretch=0)
        btn = Widgets.Button("Help")
        btn.add_callback('activated', lambda w: self.help())
        btn.set_tooltip("Show documentation for this plugin")
        btns.add_widget(btn, stretch=0)
        btn = Widgets.Button("Refresh")
        btn.add_callback('activated', lambda w: self.refresh())
        btn.set_tooltip("Refresh the file list from the directory")
        btns.add_widget(btn, stretch=0)
        btn = Widgets.Button("Load")
        btn.add_callback('activated', lambda w: self.load_cb())
        btn.set_tooltip("Load files selected in file pane")
        btns.add_widget(btn, stretch=0)
        btn = Widgets.Button("Make Thumbs")
        btn.add_callback('activated', lambda w: self.make_thumbs())
        btn.set_tooltip("Make thumbnails for files in directory")
        btns.add_widget(btn, stretch=0)

        vbox.add_widget(btns, stretch=0)

        container.add_widget(vbox, stretch=1)

    def load_paths(self, paths):
        from ginga.AstroImage import AstroImage
        from pds4_tools import pds4_read

        for path in paths:
            if self.fitsimage is not None:
                destobj = self.fitsimage
            else:
                channel = self.fv.get_channel_info()
                if channel is None:
                    return
                destobj = channel.fitsimage

            image = AstroImage(logger=self.logger, ioclass=PDS4LabelHandler)
            image.load_file(path)
            destobj.set_image(image)

    def load_cb(self):
        # Load from text box
        path = str(self.entry.get_text()).strip()
        retcode = self.open_files(path)
        if retcode:
            return

        # Load from tree view
        #curdir, curglob = os.path.split(self.curpath)
        select_dict = self.treeview.get_selected()
        paths = [info.path for key, info in select_dict.items()]
        self.logger.debug('Loading {0}'.format(paths))

        # Open directory
        if len(paths) == 1 and os.path.isdir(paths[0]):
            path = os.path.join(paths[0], '*')
            self.entry.set_text(path)
            self.browse_cb(self.entry)
            return

        # Exclude directories
        paths = [path for path in paths if os.path.isfile(path)]

        # Load files
        self.load_paths(paths)

    def makelisting(self, path):
        self.entry.set_text(path)

        tree_dict = {}
        for bnch in self.jumpinfo:
            icon = self.file_icon(bnch)
            bnch.setvals(icon=icon)
            entry_key = bnch.name

            if entry_key is None:
                raise Exception("No key for tuple")

            tree_dict[entry_key] = bnch

        self.treeview.set_tree(tree_dict)

        # Resize column widths
        n_rows = len(tree_dict)
        if n_rows < self.settings.get('max_rows_for_col_resize', 5000):
            self.treeview.set_optimal_column_widths()
            self.logger.debug("Resized columns for {0} row(s)".format(n_rows))

    def get_path_from_item(self, res_dict):
        paths = [info.path for key, info in res_dict.items()]
        path = paths[0]
        return path

    def item_dblclicked_cb(self, widget, res_dict):
        path = self.get_path_from_item(res_dict)
        self.open_file(path)

    def item_drag_cb(self, widget, drag_pkg, res_dict):
        urls = ["file://" + info.path for key, info in res_dict.items()]
        self.logger.info("urls: %s" % (urls))
        drag_pkg.set_urls(urls)

    def browse_cb(self, widget):
        path = str(widget.get_text()).strip()

        # Load file(s) -- image*.xml, image*.xml[ext]
        retcode = self.open_files(path)

        # Open directory
        if not retcode:
            self.browse(path)

    def close(self):
        if self.fitsimage is None:
            self.fv.stop_global_plugin(str(self))
        else:
            self.fv.stop_local_plugin(self.chname, str(self))
        return True

    def file_icon(self, bnch):
        if bnch.type == 'dir':
            pb = self.folderpb
        elif bnch.type == 'xml':
            pb = self.imagepb
        else:
            pb = self.filepb
        return pb

    def open_files(self, path):
        """Load file(s) -- image*.xml, image*.xml[ext].
        Returns success code (True or False).
        """
        # Strips trailing wildcard
        if path.endswith('*'):
            path = path[:-1]

        if os.path.isdir(path):
            return False

        self.logger.debug('Opening files matched by {0}'.format(path))
        info = iohelper.get_fileinfo(path)
        ext = iohelper.get_hdu_suffix(info.numhdu)
        files = glob.glob(info.filepath)  # Expand wildcard
        paths = ['{0}{1}'.format(f, ext) for f in files]

        self.load_paths(paths)
        return True

    def open_file(self, path):
        self.logger.debug("path: %s" % (path))

        if path == '..':
            curdir, curglob = os.path.split(self.curpath)
            path = os.path.join(curdir, path, curglob)

        if os.path.isdir(path):
            path = os.path.join(path, '*')
            self.browse(path)

        elif os.path.exists(path):
            #self.fv.load_file(path)
            uri = "file://%s" % (path)
            self.load_paths([uri])

        else:
            self.browse(path)

    def get_info(self, path):
        dirname, filename = os.path.split(path)
        name, ext = os.path.splitext(filename)
        ftype = 'file'
        if os.path.isdir(path):
            ftype = 'dir'
        elif os.path.islink(path):
            ftype = 'link'
        elif ext.lower() == '.xml':
            ftype = 'xml'

        bnch = Bunch.Bunch(self.na_dict)
        try:
            filestat = os.stat(path)
            bnch.update(dict(path=path, name=filename, type=ftype,
                             st_mode=filestat.st_mode,
                             st_mode_oct=oct(filestat.st_mode),
                             st_size=filestat.st_size,
                             st_size_str=str(filestat.st_size),
                             st_mtime=filestat.st_mtime,
                             st_mtime_str=time.ctime(filestat.st_mtime)))
        except OSError as e:
            # TODO: identify some kind of error with this path
            bnch.update(dict(path=path, name=filename, type=ftype,
                             st_mode=0, st_size=0,
                             st_mtime=0))

        return bnch

    def browse(self, path):
        self.logger.debug("path: %s" % (path))
        if os.path.isdir(path):
            dirname = path
            globname = None
        else:
            dirname, globname = os.path.split(path)
        dirname = os.path.abspath(dirname)

        # check validity of leading path name
        if not os.path.isdir(dirname):
            self.fv.show_error("Not a valid path: %s" % (dirname))
            return

        if not globname:
            globname = '*'
        path = os.path.join(dirname, globname)

        # Make a directory listing
        self.logger.debug("globbing path: %s" % (path))
        filelist = list(glob.glob(path))
        filelist.sort(key=lambda s: s.lower())
        filelist.insert(0, os.path.join(dirname, '..'))

        self.jumpinfo = list(map(self.get_info, filelist))
        self.curpath = path

        self.makelisting(path)

    def refresh(self):
        self.browse(self.curpath)

    def make_thumbs(self):
        path = self.curpath
        self.logger.info("Generating thumbnails for '%s'..." % (
            path))
        filelist = glob.glob(path)
        filelist.sort(key=lambda s: s.lower())

        if self.fitsimage is not None:
            # we were invoked as a local plugin
            channel = self.channel
        else:
            chviewer = self.fv.getfocus_viewer()
            # find out our channel
            chname = self.fv.get_channel_name(chviewer)
            channel = self.fv.get_channel(chname)

        self.fv.nongui_do(self._add_info, channel, filelist)

    def _add_info(self, channel, filelist):
        for path in filelist:
            name = self.fv.name_image_from_path(path)
            info = Bunch.Bunch(name=name, path=path)
            self.fv.gui_call(channel.add_image_info, info)

    def start(self):
        self.win = None
        self.browse(self.curpath)

    def pause(self):
        pass

    def resume(self):
        pass

    def stop(self):
        pass

    def redo(self, *args):
        return True

    def __str__(self):
        return 'pds4browser'


# END

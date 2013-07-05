# Copyright (C) 2008 One Laptop Per Child
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

import os
import logging
from gettext import gettext as _

import gobject
import gtk

from sugar.graphics.icon import Icon
from sugar.graphics import style
from sugar.graphics.alert import Alert

from jarabe.model.session import get_session_manager
from jarabe.controlpanel.toolbar import MainToolbar
from jarabe.controlpanel.toolbar import SectionToolbar
from jarabe import config

POWERD_FLAG_DIR = '/etc/powerd/flags'

_logger = logging.getLogger('ControlPanel')


class ControlPanel(gtk.Window):
    __gtype_name__ = 'SugarControlPanel'

    def __init__(self):
        gtk.Window.__init__(self)

        self._max_columns = int(0.285 * (float(gtk.gdk.screen_width()) /
            style.GRID_CELL_SIZE - 3))

        self.set_border_width(style.LINE_WIDTH)
        offset = style.GRID_CELL_SIZE
        width = gtk.gdk.screen_width() - offset * 2
        height = gtk.gdk.screen_height() - offset * 2
        self.set_size_request(width, height)
        self.set_position(gtk.WIN_POS_CENTER_ALWAYS)
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_modal(True)

        self._toolbar = None
        self._canvas = None
        self._table = None
        self._scrolledwindow = None
        self._separator = None
        self._section_view = None
        self._section_toolbar = None
        self._main_toolbar = None

        self._vbox = gtk.VBox()
        self._hbox = gtk.HBox()
        self._vbox.pack_start(self._hbox)
        self._hbox.show()

        self._main_view = gtk.EventBox()
        self._hbox.pack_start(self._main_view)
        self._main_view.modify_bg(gtk.STATE_NORMAL,
                                  style.COLOR_BLACK.get_gdk_color())
        self._main_view.show()

        self.add(self._vbox)
        self._vbox.show()

        self.connect('realize', self.__realize_cb)

        self._options = self._get_options()
        self._current_option = None
        self._setup_main()
        self._setup_section()
        self._show_main_view()

    def __realize_cb(self, widget):
        self.window.set_type_hint(gtk.gdk.WINDOW_TYPE_HINT_DIALOG)
        self.window.set_accept_focus(True)

    def _set_canvas(self, canvas):
        if self._canvas:
            self._main_view.remove(self._canvas)
        if canvas:
            self._main_view.add(canvas)
        self._canvas = canvas

    def _set_toolbar(self, toolbar):
        if self._toolbar:
            self._vbox.remove(self._toolbar)
        self._vbox.pack_start(toolbar, False)
        self._vbox.reorder_child(toolbar, 0)
        self._toolbar = toolbar
        if not self._separator:
            self._separator = gtk.HSeparator()
            self._vbox.pack_start(self._separator, False)
            self._vbox.reorder_child(self._separator, 1)
            self._separator.show()

    def _setup_main(self):
        self._main_toolbar = MainToolbar()

        self._table = gtk.Table()
        self._table.set_col_spacings(style.GRID_CELL_SIZE)
        self._table.set_row_spacings(style.GRID_CELL_SIZE)
        self._table.set_border_width(style.GRID_CELL_SIZE)

        self._scrolledwindow = gtk.ScrolledWindow()
        self._scrolledwindow.set_policy(gtk.POLICY_AUTOMATIC,
                                        gtk.POLICY_AUTOMATIC)
        self._scrolledwindow.add_with_viewport(self._table)
        child = self._scrolledwindow.get_child()
        child.modify_bg(gtk.STATE_NORMAL, style.COLOR_BLACK.get_gdk_color())

        self._setup_options()
        self._main_toolbar.connect('stop-clicked',
                                   self.__stop_clicked_cb)
        self._main_toolbar.connect('search-changed',
                                   self.__search_changed_cb)

    def _setup_options(self):
        if not os.access(POWERD_FLAG_DIR, os.W_OK):
            del self._options['power']

        try:
            import xklavier
        except ImportError:
            del self._options['keyboard']

        # If the screen width only supports two columns, start
        # placing from the second row.
        if self._max_columns == 2:
            row = 1
            column = 0
        else:
            # About Me and About my computer are hardcoded below to use the
            # first two slots so we need to leave them free.
            row = 0
            column = 2

        options = self._options.keys()
        options.sort()

        for option in options:
            sectionicon = _SectionIcon(icon_name=self._options[option]['icon'],
                                       title=self._options[option]['title'],
                                       xo_color=self._options[option]['color'],
                                       pixel_size=style.GRID_CELL_SIZE)
            sectionicon.connect('button_press_event',
                               self.__select_option_cb, option)
            sectionicon.show()

            if option == 'aboutme':
                self._table.attach(sectionicon, 0, 1, 0, 1)
            elif option == 'aboutcomputer':
                self._table.attach(sectionicon, 1, 2, 0, 1)
            else:
                self._table.attach(sectionicon,
                                   column, column + 1,
                                   row, row + 1)
                column += 1
                if column == self._max_columns:
                    column = 0
                    row += 1

            self._options[option]['button'] = sectionicon

    def _show_main_view(self):
        self._set_toolbar(self._main_toolbar)
        self._main_toolbar.show()
        self._set_canvas(self._scrolledwindow)
        self._main_view.modify_bg(gtk.STATE_NORMAL,
                                  style.COLOR_BLACK.get_gdk_color())
        self._table.show()
        self._scrolledwindow.show()
        entry = self._main_toolbar.get_entry()
        entry.grab_focus()
        entry.set_text('')

    def _update(self, query):
        for option in self._options:
            found = False
            for key in self._options[option]['keywords']:
                if query.lower() in key.lower():
                    self._options[option]['button'].set_sensitive(True)
                    found = True
                    break
            if not found:
                self._options[option]['button'].set_sensitive(False)

    def _setup_section(self):
        self._section_toolbar = SectionToolbar()
        self._section_toolbar.connect('cancel-clicked',
                                     self.__cancel_clicked_cb)
        self._section_toolbar.connect('accept-clicked',
                                     self.__accept_clicked_cb)

    def show_section_view(self, option):
        self._set_toolbar(self._section_toolbar)

        icon = self._section_toolbar.get_icon()
        icon.set_from_icon_name(self._options[option]['icon'],
                                gtk.ICON_SIZE_LARGE_TOOLBAR)
        icon.props.xo_color = self._options[option]['color']
        title = self._section_toolbar.get_title()
        title.set_text(self._options[option]['title'])
        self._section_toolbar.show()

        self._current_option = option

        mod = __import__('.'.join(('cpsection', option, 'view')),
                         globals(), locals(), ['view'])
        view_class = getattr(mod, self._options[option]['view'], None)

        mod = __import__('.'.join(('cpsection', option, 'model')),
                         globals(), locals(), ['model'])
        model = ModelWrapper(mod)

        try:
            self.get_window().set_cursor(gtk.gdk.Cursor(gtk.gdk.WATCH))
            self._section_view = view_class(model,
                                            self._options[option]['alerts'])

            self._set_canvas(self._section_view)
            self._section_view.show()
        finally:
            self.get_window().set_cursor(None)

        self._section_view.connect('notify::is-valid',
                                   self.__valid_section_cb)
        self._section_view.connect('request-close',
                                   self.__close_request_cb)
        self._main_view.modify_bg(gtk.STATE_NORMAL,
                                  style.COLOR_WHITE.get_gdk_color())

    def set_section_view_auto_close(self):
        """Automatically close the control panel if there is "nothing to do"
        """
        self._section_view.auto_close = True

    def _get_options(self):
        """Get the available option information from the extensions
        """
        options = {}

        path = os.path.join(config.ext_path, 'cpsection')
        folder = os.listdir(path)

        for item in folder:
            if os.path.isdir(os.path.join(path, item)) and \
                    os.path.exists(os.path.join(path, item, '__init__.py')):
                try:
                    mod = __import__('.'.join(('cpsection', item)),
                                     globals(), locals(), [item])
                    view_class = getattr(mod, 'CLASS', None)
                    if view_class is not None:
                        options[item] = {}
                        options[item]['alerts'] = []
                        options[item]['view'] = view_class
                        options[item]['icon'] = getattr(mod, 'ICON', item)
                        options[item]['title'] = getattr(mod, 'TITLE', item)
                        options[item]['color'] = getattr(mod, 'COLOR', None)
                        keywords = getattr(mod, 'KEYWORDS', [])
                        keywords.append(options[item]['title'].lower())
                        if item not in keywords:
                            keywords.append(item)
                        options[item]['keywords'] = keywords
                    else:
                        _logger.error('no CLASS attribute in %r', item)
                except Exception:
                    logging.exception('Exception while loading extension:')

        return options

    def __cancel_clicked_cb(self, widget):
        self._section_view.undo()
        self._options[self._current_option]['alerts'] = []
        self._section_toolbar.accept_button.set_sensitive(True)
        self._show_main_view()

    def __accept_clicked_cb(self, widget):
        if self._section_view.needs_restart:
            self._section_toolbar.accept_button.set_sensitive(False)
            self._section_toolbar.cancel_button.set_sensitive(False)
            alert = Alert()
            alert.props.title = _('Warning')
            alert.props.msg = _('Changes require restart')

            icon = Icon(icon_name='dialog-cancel')
            alert.add_button(gtk.RESPONSE_CANCEL, _('Cancel changes'), icon)
            icon.show()

            if self._current_option != 'aboutme':
                icon = Icon(icon_name='dialog-ok')
                alert.add_button(gtk.RESPONSE_ACCEPT, _('Later'), icon)
                icon.show()

            icon = Icon(icon_name='system-restart')
            alert.add_button(gtk.RESPONSE_APPLY, _('Restart now'), icon)
            icon.show()

            self._vbox.pack_start(alert, False)
            self._vbox.reorder_child(alert, 2)
            alert.connect('response', self.__response_cb)
            alert.show()
        else:
            self._show_main_view()

    def __response_cb(self, alert, response_id):
        self._vbox.remove(alert)
        self._section_toolbar.accept_button.set_sensitive(True)
        self._section_toolbar.cancel_button.set_sensitive(True)
        if response_id is gtk.RESPONSE_CANCEL:
            self._section_view.undo()
            self._section_view.setup()
            self._options[self._current_option]['alerts'] = []
        elif response_id is gtk.RESPONSE_ACCEPT:
            self._options[self._current_option]['alerts'] = \
                self._section_view.restart_alerts
            self._show_main_view()
        elif response_id is gtk.RESPONSE_APPLY:
            session_manager = get_session_manager()
            session_manager.logout()

    def __select_option_cb(self, button, event, option):
        self.show_section_view(option)

    def __search_changed_cb(self, maintoolbar, query):
        self._update(query)

    def __stop_clicked_cb(self, widget):
        self.destroy()

    def __close_request_cb(self, widget, event=None):
        self.destroy()

    def __valid_section_cb(self, section_view, pspec):
        section_is_valid = section_view.props.is_valid
        self._section_toolbar.accept_button.set_sensitive(section_is_valid)


class ModelWrapper(object):
    def __init__(self, module):
        self._module = module
        self._options = {}
        self._setup()

    def _setup(self):
        methods = dir(self._module)
        for method in methods:
            if method.startswith('get_') and method[4:] != 'color':
                try:
                    self._options[method[4:]] = getattr(self._module, method)()
                except Exception:
                    self._options[method[4:]] = None

    def __getattr__(self, name):
        return getattr(self._module, name)

    def undo(self):
        for key in self._options.keys():
            method = getattr(self._module, 'set_' + key, None)
            if method and self._options[key] is not None:
                try:
                    method(self._options[key])
                except Exception, detail:
                    _logger.debug('Error undo option: %s', detail)


class _SectionIcon(gtk.EventBox):
    __gtype_name__ = 'SugarSectionIcon'

    __gproperties__ = {
        'icon-name': (str, None, None, None, gobject.PARAM_READWRITE),
        'pixel-size': (object, None, None, gobject.PARAM_READWRITE),
        'xo-color': (object, None, None, gobject.PARAM_READWRITE),
        'title': (str, None, None, None, gobject.PARAM_READWRITE),
    }

    def __init__(self, **kwargs):
        self._icon_name = None
        self._pixel_size = style.GRID_CELL_SIZE
        self._xo_color = None
        self._title = 'No Title'

        gobject.GObject.__init__(self, **kwargs)

        self._vbox = gtk.VBox()
        self._icon = Icon(icon_name=self._icon_name,
                          pixel_size=self._pixel_size,
                          xo_color=self._xo_color)
        self._vbox.pack_start(self._icon, expand=False, fill=False)

        self._label = gtk.Label(self._title)
        self._label.modify_fg(gtk.STATE_NORMAL,
                              style.COLOR_WHITE.get_gdk_color())
        self._vbox.pack_start(self._label, expand=False, fill=False)

        self._vbox.set_spacing(style.DEFAULT_SPACING)
        self.set_visible_window(False)
        self.set_app_paintable(True)
        self.set_events(gtk.gdk.BUTTON_PRESS_MASK)

        self.add(self._vbox)
        self._vbox.show()
        self._label.show()
        self._icon.show()

    def get_icon(self):
        return self._icon

    def do_set_property(self, pspec, value):
        if pspec.name == 'icon-name':
            if self._icon_name != value:
                self._icon_name = value
        elif pspec.name == 'pixel-size':
            if self._pixel_size != value:
                self._pixel_size = value
        elif pspec.name == 'xo-color':
            if self._xo_color != value:
                self._xo_color = value
        elif pspec.name == 'title':
            if self._title != value:
                self._title = value

    def do_get_property(self, pspec):
        if pspec.name == 'icon-name':
            return self._icon_name
        elif pspec.name == 'pixel-size':
            return self._pixel_size
        elif pspec.name == 'xo-color':
            return self._xo_color
        elif pspec.name == 'title':
            return self._title

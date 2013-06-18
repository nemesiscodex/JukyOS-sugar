# Copyright (C) 2007, Red Hat, Inc.
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

import gtk
import gobject
import wnck
import gconf


_MAX_DELAY = 1000


class EventArea(gobject.GObject):
    __gsignals__ = {
        'enter': (gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE, ([])),
        'leave': (gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE, ([])),
    }

    def __init__(self):
        gobject.GObject.__init__(self)

        self._windows = []
        self._hover = False
        self._sids = {}
        client = gconf.client_get_default()
        self._edge_delay = client.get_int('/desktop/sugar/frame/edge_delay')
        self._corner_delay = client.get_int('/desktop/sugar/frame'
                                            '/corner_delay')

        right = gtk.gdk.screen_width() - 1
        bottom = gtk.gdk.screen_height() - 1
        width = gtk.gdk.screen_width() - 2
        height = gtk.gdk.screen_height() - 2

        if self._edge_delay != _MAX_DELAY:
            invisible = self._create_invisible(1, 0, width, 1,
                                               self._edge_delay)
            self._windows.append(invisible)

            invisible = self._create_invisible(1, bottom, width, 1,
                                               self._edge_delay)
            self._windows.append(invisible)

            invisible = self._create_invisible(0, 1, 1, height,
                                               self._edge_delay)
            self._windows.append(invisible)

            invisible = self._create_invisible(right, 1, 1, height,
                                               self._edge_delay)
            self._windows.append(invisible)

        if self._corner_delay != _MAX_DELAY:
            invisible = self._create_invisible(0, 0, 1, 1,
                                               self._corner_delay)
            self._windows.append(invisible)

            invisible = self._create_invisible(right, 0, 1, 1,
                                               self._corner_delay)
            self._windows.append(invisible)

            invisible = self._create_invisible(0, bottom, 1, 1,
                                               self._corner_delay)
            self._windows.append(invisible)

            invisible = self._create_invisible(right, bottom, 1, 1,
                                               self._corner_delay)
            self._windows.append(invisible)

        screen = wnck.screen_get_default()
        screen.connect('window-stacking-changed',
                       self._window_stacking_changed_cb)

    def _create_invisible(self, x, y, width, height, delay):
        invisible = gtk.Invisible()
        if delay >= 0:
            invisible.connect('enter-notify-event', self._enter_notify_cb,
                              delay)
            invisible.connect('leave-notify-event', self._leave_notify_cb)

        invisible.drag_dest_set(0, [], 0)
        invisible.connect('drag_motion', self._drag_motion_cb)
        invisible.connect('drag_leave', self._drag_leave_cb)

        invisible.realize()
        # pylint: disable=E1101
        invisible.window.set_events(gtk.gdk.POINTER_MOTION_MASK |
                                    gtk.gdk.ENTER_NOTIFY_MASK |
                                    gtk.gdk.LEAVE_NOTIFY_MASK)
        invisible.window.move_resize(x, y, width, height)

        return invisible

    def _notify_enter(self):
        if not self._hover:
            self._hover = True
            self.emit('enter')

    def _notify_leave(self):
        if self._hover:
            self._hover = False
            self.emit('leave')

    def _enter_notify_cb(self, widget, event, delay):
        if widget in self._sids:
            gobject.source_remove(self._sids[widget])
        self._sids[widget] = gobject.timeout_add(delay,
                                                 self.__delay_cb,
                                                 widget)

    def __delay_cb(self, widget):
        del self._sids[widget]
        self._notify_enter()
        return False

    def _leave_notify_cb(self, widget, event):
        if widget in self._sids:
            gobject.source_remove(self._sids[widget])
            del self._sids[widget]
        self._notify_leave()

    def _drag_motion_cb(self, widget, drag_context, x, y, timestamp):
        drag_context.drag_status(0, timestamp)
        self._notify_enter()
        return True

    def _drag_leave_cb(self, widget, drag_context, timestamp):
        self._notify_leave()
        return True

    def show(self):
        for window in self._windows:
            window.show()

    def hide(self):
        for window in self._windows:
            window.hide()

    def _window_stacking_changed_cb(self, screen):
        for window in self._windows:
            window.window.raise_()

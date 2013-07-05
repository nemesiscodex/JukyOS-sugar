# Copyright (C) 2006-2007 Red Hat, Inc.
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

import logging

import gtk
import gobject

from sugar.graphics import animator
from sugar.graphics import style
from sugar.graphics import palettegroup
from sugar import profile

from jarabe.frame.eventarea import EventArea
from jarabe.frame.activitiestray import ActivitiesTray
from jarabe.frame.zoomtoolbar import ZoomToolbar
from jarabe.frame.friendstray import FriendsTray
from jarabe.frame.devicestray import DevicesTray
from jarabe.frame.framewindow import FrameWindow
from jarabe.frame.clipboardpanelwindow import ClipboardPanelWindow
from jarabe.frame.notification import NotificationIcon, NotificationWindow
from jarabe.model import notifications


TOP_RIGHT = 0
TOP_LEFT = 1
BOTTOM_RIGHT = 2
BOTTOM_LEFT = 3

_FRAME_HIDING_DELAY = 500
_NOTIFICATION_DURATION = 5000


class _Animation(animator.Animation):
    def __init__(self, frame, end):
        start = frame.current_position
        animator.Animation.__init__(self, start, end)
        self._frame = frame

    def next_frame(self, current):
        self._frame.move(current)


class _MouseListener(object):
    def __init__(self, frame):
        self._frame = frame
        self._hide_sid = 0

    def mouse_enter(self):
        self._show_frame()

    def mouse_leave(self):
        if self._frame.mode == Frame.MODE_MOUSE:
            self._hide_frame()

    def _show_frame(self):
        if self._hide_sid != 0:
            gobject.source_remove(self._hide_sid)
        self._frame.show(Frame.MODE_MOUSE)

    def _hide_frame_timeout_cb(self):
        self._frame.hide()
        return False

    def _hide_frame(self):
        if self._hide_sid != 0:
            gobject.source_remove(self._hide_sid)
        self._hide_sid = gobject.timeout_add(
                  _FRAME_HIDING_DELAY, self._hide_frame_timeout_cb)


class _KeyListener(object):
    def __init__(self, frame):
        self._frame = frame

    def key_press(self):
        if self._frame.visible:
            if self._frame.mode == Frame.MODE_KEYBOARD:
                self._frame.hide()
        else:
            self._frame.show(Frame.MODE_KEYBOARD)


class Frame(object):
    MODE_MOUSE = 0
    MODE_KEYBOARD = 1
    MODE_NON_INTERACTIVE = 2

    def __init__(self):
        logging.debug('STARTUP: Loading the frame')
        self.mode = None

        self._palette_group = palettegroup.get_group('frame')
        self._palette_group.connect('popdown', self._palette_group_popdown_cb)

        self._left_panel = None
        self._right_panel = None
        self._top_panel = None
        self._bottom_panel = None

        self.current_position = 0.0
        self._animator = None

        self._event_area = EventArea()
        self._event_area.connect('enter', self._enter_corner_cb)
        self._event_area.show()

        self._top_panel = self._create_top_panel()
        self._bottom_panel = self._create_bottom_panel()
        self._left_panel = self._create_left_panel()
        self._right_panel = self._create_right_panel()

        screen = gtk.gdk.screen_get_default()
        screen.connect('size-changed', self._size_changed_cb)

        self._key_listener = _KeyListener(self)
        self._mouse_listener = _MouseListener(self)

        self._notif_by_icon = {}

        notification_service = notifications.get_service()
        notification_service.notification_received.connect(
                self.__notification_received_cb)
        notification_service.notification_cancelled.connect(
                self.__notification_cancelled_cb)

    def is_visible(self):
        return self.current_position != 0.0

    visible = property(is_visible, None)

    def hide(self):
        if self._animator:
            self._animator.stop()

        self._animator = animator.Animator(0.5)
        self._animator.add(_Animation(self, 0.0))
        self._animator.start()

        self.mode = None

    def show(self, mode):
        if self.visible:
            return
        if self._animator:
            self._animator.stop()

        self.mode = mode

        self._animator = animator.Animator(0.5)
        self._animator.add(_Animation(self, 1.0))
        self._animator.start()

    def move(self, pos):
        self.current_position = pos
        self._update_position()

    def _is_hover(self):
        return (self._top_panel.hover or \
                self._bottom_panel.hover or \
                self._left_panel.hover or \
                self._right_panel.hover)

    def _create_top_panel(self):
        panel = self._create_panel(gtk.POS_TOP)

        zoom_toolbar = ZoomToolbar()
        panel.append(zoom_toolbar, expand=False)
        zoom_toolbar.show()

        activities_tray = ActivitiesTray()
        panel.append(activities_tray)
        activities_tray.show()

        return panel

    def _create_bottom_panel(self):
        panel = self._create_panel(gtk.POS_BOTTOM)

        devices_tray = DevicesTray()
        panel.append(devices_tray)
        devices_tray.show()

        return panel

    def _create_right_panel(self):
        panel = self._create_panel(gtk.POS_RIGHT)

        tray = FriendsTray()
        panel.append(tray)
        tray.show()

        return panel

    def _create_left_panel(self):
        panel = ClipboardPanelWindow(self, gtk.POS_LEFT)

        self._connect_to_panel(panel)
        panel.connect('drag-motion', self._drag_motion_cb)
        panel.connect('drag-leave', self._drag_leave_cb)

        return panel

    def _create_panel(self, orientation):
        panel = FrameWindow(orientation)
        self._connect_to_panel(panel)

        return panel

    def _move_panel(self, panel, pos, x1, y1, x2, y2):
        x = (x2 - x1) * pos + x1
        y = (y2 - y1) * pos + y1

        panel.move(int(x), int(y))

        # FIXME we should hide and show as necessary to free memory
        if not panel.props.visible:
            panel.show()

    def _connect_to_panel(self, panel):
        panel.connect('enter-notify-event', self._enter_notify_cb)
        panel.connect('leave-notify-event', self._leave_notify_cb)

    def _update_position(self):
        screen_h = gtk.gdk.screen_height()
        screen_w = gtk.gdk.screen_width()

        self._move_panel(self._top_panel, self.current_position,
                         0, - self._top_panel.size, 0, 0)

        self._move_panel(self._bottom_panel, self.current_position,
                         0, screen_h, 0, screen_h - self._bottom_panel.size)

        self._move_panel(self._left_panel, self.current_position,
                         - self._left_panel.size, 0, 0, 0)

        self._move_panel(self._right_panel, self.current_position,
                         screen_w, 0, screen_w - self._right_panel.size, 0)

    def _size_changed_cb(self, screen):
        self._update_position()

    def _enter_notify_cb(self, window, event):
        if event.detail != gtk.gdk.NOTIFY_INFERIOR:
            self._mouse_listener.mouse_enter()

    def _leave_notify_cb(self, window, event):
        if event.detail == gtk.gdk.NOTIFY_INFERIOR:
            return

        if not self._is_hover() and not self._palette_group.is_up():
            self._mouse_listener.mouse_leave()

    def _palette_group_popdown_cb(self, group):
        if not self._is_hover():
            self._mouse_listener.mouse_leave()

    def _drag_motion_cb(self, window, context, x, y, time):
        self._mouse_listener.mouse_enter()

    def _drag_leave_cb(self, window, drag_context, timestamp):
        self._mouse_listener.mouse_leave()

    def _enter_corner_cb(self, event_area):
        self._mouse_listener.mouse_enter()

    def notify_key_press(self):
        self._key_listener.key_press()

    def add_notification(self, icon, corner=gtk.CORNER_TOP_LEFT,
                         duration=_NOTIFICATION_DURATION):

        if not isinstance(icon, NotificationIcon):
            raise TypeError('icon must be a NotificationIcon.')

        window = NotificationWindow()

        screen = gtk.gdk.screen_get_default()
        if corner == gtk.CORNER_TOP_LEFT:
            window.move(0, 0)
        elif corner == gtk.CORNER_TOP_RIGHT:
            window.move(screen.get_width() - style.GRID_CELL_SIZE, 0)
        elif corner == gtk.CORNER_BOTTOM_LEFT:
            window.move(0, screen.get_height() - style.GRID_CELL_SIZE)
        elif corner == gtk.CORNER_BOTTOM_RIGHT:
            window.move(screen.get_width() - style.GRID_CELL_SIZE,
                        screen.get_height() - style.GRID_CELL_SIZE)
        else:
            raise ValueError('Inalid corner: %r' % corner)

        window.add(icon)
        icon.show()
        window.show()

        self._notif_by_icon[icon] = window

        gobject.timeout_add(duration,
                        lambda: self.remove_notification(icon))

    def remove_notification(self, icon):
        if icon not in self._notif_by_icon:
            logging.debug('icon %r not in list of notifications.', icon)
            return

        window = self._notif_by_icon[icon]
        window.destroy()
        del self._notif_by_icon[icon]

    def __notification_received_cb(self, **kwargs):
        logging.debug('__notification_received_cb')
        icon = NotificationIcon()

        hints = kwargs['hints']

        icon_file_name = hints.get('x-sugar-icon-file-name', '')
        if icon_file_name:
            icon.props.icon_filename = icon_file_name
        else:
            icon.props.icon_name = 'application-octet-stream'

        icon_colors = hints.get('x-sugar-icon-colors', '')
        if not icon_colors:
            icon_colors = profile.get_color()
        icon.props.xo_color = icon_colors

        duration = kwargs.get('expire_timeout', -1)
        if duration == -1:
            duration = _NOTIFICATION_DURATION

        self.add_notification(icon, gtk.CORNER_TOP_RIGHT, duration)

    def __notification_cancelled_cb(self, **kwargs):
        # Do nothing for now. Our notification UI is so simple, there's no
        # point yet.
        pass

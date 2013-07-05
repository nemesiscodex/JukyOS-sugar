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
import statvfs
from gettext import gettext as _
import logging

import gconf
import glib
import gtk

from sugar import env
from sugar.graphics.palette import Palette
from sugar.graphics.menuitem import MenuItem
from sugar.graphics.icon import Icon
from sugar.graphics import style
from sugar.graphics.xocolor import XoColor
from sugar.activity.i18n import pgettext

from jarabe.model import shell
from jarabe.view.viewsource import setup_view_source
from jarabe.journal import misc


class BasePalette(Palette):
    def __init__(self, home_activity):
        Palette.__init__(self)

        self._notify_launch_hid = None

        if home_activity.props.launch_status == shell.Activity.LAUNCHING:
            self._notify_launch_hid = home_activity.connect( \
                    'notify::launch-status', self.__notify_launch_status_cb)
            self.set_primary_text(glib.markup_escape_text(_('Starting...')))
        elif home_activity.props.launch_status == shell.Activity.LAUNCH_FAILED:
            self._on_failed_launch()
        else:
            self.setup_palette()

    def setup_palette(self):
        raise NotImplementedError

    def _on_failed_launch(self):
        message = _('Activity failed to start')
        self.set_primary_text(glib.markup_escape_text(message))

    def __notify_launch_status_cb(self, home_activity, pspec):
        home_activity.disconnect(self._notify_launch_hid)
        self._notify_launch_hid = None
        if home_activity.props.launch_status == shell.Activity.LAUNCH_FAILED:
            self._on_failed_launch()
        else:
            self.setup_palette()


class CurrentActivityPalette(BasePalette):
    def __init__(self, home_activity):
        self._home_activity = home_activity
        BasePalette.__init__(self, home_activity)

    def setup_palette(self):
        activity_name = self._home_activity.get_activity_name()
        if activity_name:
            self.props.primary_text = glib.markup_escape_text(activity_name)

        title = self._home_activity.get_title()
        if title and title != activity_name:
            self.props.secondary_text = glib.markup_escape_text(title)

        menu_item = MenuItem(_('Resume'), 'activity-start')
        menu_item.connect('activate', self.__resume_activate_cb)
        self.menu.append(menu_item)
        menu_item.show()

        # TODO: share-with, keep

        menu_item = MenuItem(_('View Source'), 'view-source')
        # TODO Make this accelerator translatable
        menu_item.props.accelerator = '<Alt><Shift>v'
        menu_item.connect('activate', self.__view_source__cb)
        self.menu.append(menu_item)
        menu_item.show()

        separator = gtk.SeparatorMenuItem()
        self.menu.append(separator)
        separator.show()

        menu_item = MenuItem(_('Stop'), 'activity-stop')
        menu_item.connect('activate', self.__stop_activate_cb)
        self.menu.append(menu_item)
        menu_item.show()

    def __resume_activate_cb(self, menu_item):
        self._home_activity.get_window().activate(gtk.get_current_event_time())

    def __view_source__cb(self, menu_item):
        setup_view_source(self._home_activity)
        shell_model = shell.get_model()
        if self._home_activity is not shell_model.get_active_activity():
            self._home_activity.get_window().activate( \
                gtk.get_current_event_time())

    def __stop_activate_cb(self, menu_item):
        self._home_activity.get_window().close(1)


class ActivityPalette(Palette):
    __gtype_name__ = 'SugarActivityPalette'

    def __init__(self, activity_info):
        self._activity_info = activity_info

        client = gconf.client_get_default()
        color = XoColor(client.get_string('/desktop/sugar/user/color'))
        activity_icon = Icon(file=activity_info.get_icon(),
                             xo_color=color,
                             icon_size=gtk.ICON_SIZE_LARGE_TOOLBAR)

        name = activity_info.get_name()
        Palette.__init__(self, primary_text=glib.markup_escape_text(name),
                         icon=activity_icon)

        xo_color = XoColor('%s,%s' % (style.COLOR_WHITE.get_svg(),
                                      style.COLOR_TRANSPARENT.get_svg()))
        menu_item = MenuItem(text_label=_('Start new'),
                             file_name=activity_info.get_icon(),
                             xo_color=xo_color)
        menu_item.connect('activate', self.__start_activate_cb)
        self.menu.append(menu_item)
        menu_item.show()

        # TODO: start-with

    def __start_activate_cb(self, menu_item):
        self.popdown(immediate=True)
        misc.launch(self._activity_info)


class JournalPalette(BasePalette):
    def __init__(self, home_activity):
        self._home_activity = home_activity
        self._progress_bar = None
        self._free_space_label = None

        BasePalette.__init__(self, home_activity)

    def setup_palette(self):
        title = self._home_activity.get_title()
        self.set_primary_text(glib.markup_escape_text(title))

        vbox = gtk.VBox()
        self.set_content(vbox)
        vbox.show()

        self._progress_bar = gtk.ProgressBar()
        vbox.add(self._progress_bar)
        self._progress_bar.show()

        self._free_space_label = gtk.Label()
        self._free_space_label.set_alignment(0.5, 0.5)
        vbox.add(self._free_space_label)
        self._free_space_label.show()

        self.connect('popup', self.__popup_cb)

        menu_item = MenuItem(_('Show contents'))

        icon = Icon(file=self._home_activity.get_icon_path(),
                icon_size=gtk.ICON_SIZE_MENU,
                xo_color=self._home_activity.get_icon_color())
        menu_item.set_image(icon)
        icon.show()

        menu_item.connect('activate', self.__open_activate_cb)
        self.menu.append(menu_item)
        menu_item.show()

    def __open_activate_cb(self, menu_item):
        self._home_activity.get_window().activate(gtk.get_current_event_time())

    def __popup_cb(self, palette):
        stat = os.statvfs(env.get_profile_path())
        free_space = stat[statvfs.F_BSIZE] * stat[statvfs.F_BAVAIL]
        total_space = stat[statvfs.F_BSIZE] * stat[statvfs.F_BLOCKS]

        fraction = (total_space - free_space) / float(total_space)
        self._progress_bar.props.fraction = fraction
        self._free_space_label.props.label = _('%(free_space)d MB Free') % \
                {'free_space': free_space / (1024 * 1024)}


class VolumePalette(Palette):
    def __init__(self, mount):
        Palette.__init__(self, label=mount.get_name())
        self._mount = mount

        path = mount.get_root().get_path()
        self.props.secondary_text = glib.markup_escape_text(path)

        vbox = gtk.VBox()
        self.set_content(vbox)
        vbox.show()

        self._progress_bar = gtk.ProgressBar()
        vbox.add(self._progress_bar)
        self._progress_bar.show()

        self._free_space_label = gtk.Label()
        self._free_space_label.set_alignment(0.5, 0.5)
        vbox.add(self._free_space_label)
        self._free_space_label.show()

        self.connect('popup', self.__popup_cb)

        menu_item = MenuItem(pgettext('Volume', 'Remove'))

        icon = Icon(icon_name='media-eject', icon_size=gtk.ICON_SIZE_MENU)
        menu_item.set_image(icon)
        icon.show()

        menu_item.connect('activate', self.__unmount_activate_cb)
        self.menu.append(menu_item)
        menu_item.show()

    def __unmount_activate_cb(self, menu_item):
        self._mount.unmount(self.__unmount_cb)

    def __unmount_cb(self, mount, result):
        logging.debug('__unmount_cb %r %r', mount, result)
        mount.unmount_finish(result)

    def __popup_cb(self, palette):
        mount_point = self._mount.get_root().get_path()
        stat = os.statvfs(mount_point)
        free_space = stat[statvfs.F_BSIZE] * stat[statvfs.F_BAVAIL]
        total_space = stat[statvfs.F_BSIZE] * stat[statvfs.F_BLOCKS]

        fraction = (total_space - free_space) / float(total_space)
        self._progress_bar.props.fraction = fraction
        self._free_space_label.props.label = _('%(free_space)d MB Free') % \
                {'free_space': free_space / (1024 * 1024)}

#!/usr/bin/env python
# Copyright (C) 2010, Plan Ceibal <comunidad@plan.ceibal.edu.uy>
# Copyright (C) 2010, Paraguay Educa <tecnologia@paraguayeduca.org>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import gtk
import gobject
import gconf
import logging

from gettext import gettext as _
from sugar.graphics import style
from sugar.graphics.icon import Icon
from sugar.graphics.xocolor import XoColor

from jarabe.journal import misc
from jarabe.model import shell
from jarabe.model import processmanagement
from jarabe.model.session import get_session_manager

class ProcessDialog(gtk.Window):

    __gtype_name__ = 'SugarProcessDialog'

    def __init__(self, process_script='', process_params=[], restart_after=True):

        #FIXME: Workaround limitations of Sugar core modal handling
        shell_model = shell.get_model()
        shell_model.set_zoom_level(shell_model.ZOOM_HOME)

        gtk.Window.__init__(self)

        self._process_script = processmanagement.find_and_absolutize(process_script)
        self._process_params = process_params
        self._restart_after = restart_after
        self._start_message = _('Running')
        self._failed_message = _('Failed')
        self._finished_message = _('Finished')
        self._prerequisite_message = ('Prerequisites were not met')

        self.set_border_width(style.LINE_WIDTH)
        width = gtk.gdk.screen_width()
        height = gtk.gdk.screen_height()
        self.set_size_request(width, height)
        self.set_position(gtk.WIN_POS_CENTER_ALWAYS)
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_modal(True)

        self._colored_box = gtk.EventBox()
        self._colored_box.modify_bg(gtk.STATE_NORMAL, gtk.gdk.color_parse("white"))
        self._colored_box.show()

        self._vbox = gtk.VBox()
        self._vbox.set_spacing(style.DEFAULT_SPACING)
        self._vbox.set_border_width(style.GRID_CELL_SIZE)

        self._colored_box.add(self._vbox)
        self.add(self._colored_box)

        self._setup_information()
        self._setup_progress_bar()
        self._setup_options()

        self._vbox.show()

        self.connect("realize", self.__realize_cb)

        self._process_management = processmanagement.ProcessManagement()
        self._process_management.connect('process-management-running', self._set_status_updated)
        self._process_management.connect('process-management-started', self._set_status_started)
        self._process_management.connect('process-management-finished', self._set_status_finished)
        self._process_management.connect('process-management-failed', self._set_status_failed)

    def _setup_information(self):
        client = gconf.client_get_default()
        color = XoColor(client.get_string('/desktop/sugar/user/color'))

        self._icon = Icon(icon_name='activity-journal', pixel_size=style.XLARGE_ICON_SIZE, xo_color=color)
        self._icon.show()

        self._vbox.pack_start(self._icon, False)

        self._title = gtk.Label()
        self._title.modify_fg(gtk.STATE_NORMAL, style.COLOR_BLACK.get_gdk_color())
        self._title.set_use_markup(True)
        self._title.set_justify(gtk.JUSTIFY_CENTER)
        self._title.show()

        self._vbox.pack_start(self._title, False)

        self._message = gtk.Label()
        self._message.modify_fg(gtk.STATE_NORMAL, style.COLOR_BLACK.get_gdk_color())
        self._message.set_use_markup(True)
        self._message.set_line_wrap(True)
        self._message.set_justify(gtk.JUSTIFY_CENTER)
        self._message.show()

        self._vbox.pack_start(self._message, True)

    def _setup_options(self):
        hbox = gtk.HBox(True, 3)
        hbox.show()

        icon = Icon(icon_name='dialog-ok')

        self._start_button = gtk.Button()
        self._start_button.set_image(icon)
        self._start_button.set_label(_('Start'))
        self._start_button.connect('clicked', self.__start_cb)
        self._start_button.show()

        icon = Icon(icon_name='dialog-cancel')

        self._close_button = gtk.Button()
        self._close_button.set_image(icon)
        self._close_button.set_label(_('Close'))
        self._close_button.connect('clicked', self.__close_cb)
        self._close_button.show()

        icon = Icon(icon_name='system-restart')

        self._restart_button = gtk.Button()
        self._restart_button.set_image(icon)
        self._restart_button.set_label(_('Restart'))
        self._restart_button.connect('clicked', self.__restart_cb)
        self._restart_button.hide()

        hbox.add(self._start_button)
        hbox.add(self._close_button)
        hbox.add(self._restart_button)

        halign = gtk.Alignment(1, 0, 0, 0)
        halign.show()
        halign.add(hbox)

        self._vbox.pack_start(halign, False, False, 3)

    def _setup_progress_bar(self):
        alignment = gtk.Alignment(xalign=0.5, yalign=0.5, xscale=0.5)
        alignment.show()

        self._progress_bar = gtk.ProgressBar(adjustment=None)
        self._progress_bar.hide()

        alignment.add(self._progress_bar)
        self._vbox.pack_start(alignment)

    def __realize_cb(self, widget):
        self.window.set_type_hint(gtk.gdk.WINDOW_TYPE_HINT_DIALOG)
        self.window.set_accept_focus(True)

    def __close_cb(self, button):
        self.destroy()

    def __start_cb(self, button):
        if self._check_prerequisites():
            self._process_management.do_process([self._process_script] + self._process_params)
        else:
            self._set_status_failed(self, error_message=self._prerequisite_message)

    def __restart_cb(self, button):
        session_manager = get_session_manager()
        session_manager.logout()

    def _check_prerequisites(self):
        return True

    def _set_status_started(self, model, data=None):
        self._message.set_markup(self._start_message)

        self._start_button.hide()
        self._close_button.hide()

        self._progress_bar.set_fraction(0.05)
        self._progress_bar_handler = gobject.timeout_add(1000, self.__progress_bar_handler_cb)
        self._progress_bar.show()

    def __progress_bar_handler_cb(self):
        self._progress_bar.pulse()
        return True

    def _set_status_updated(self, model, data):
        pass

    def _set_status_finished(self, model, data=None):
        self._message.set_markup(self._finished_message)

        self._progress_bar.hide()
        self._start_button.hide()

        if self._restart_after:
            self._restart_button.show()
        else:
            self._close_button.show()

    def _set_status_failed(self, model=None, error_message=''):
        self._message.set_markup('%s %s' % (self._failed_message, error_message))

        self._progress_bar.hide()
        self._start_button.show()
        self._close_button.show()
        self._restart_button.hide()

        logging.error(error_message)


class VolumeBackupDialog(ProcessDialog):

    def __init__(self, volume_path):
        ProcessDialog.__init__(self, 'journal-backup-volume', \
                              [volume_path, misc.get_backup_identifier()], restart_after=False)

        self._resetup_information(volume_path)

    def _resetup_information(self, volume_path):
        self._start_message = '%s %s. \n\n' % (_('Please wait, saving Journal content to'), volume_path) + \
                              '<big><b>%s</b></big>' % _('Do not remove the storage device!')

        self._finished_message = _('The Journal content has been saved.')

        self._title.set_markup('<big><b>%s</b></big>' % _('Backup'))

        self._message.set_markup('%s %s' % (_('Journal content will be saved to'), volume_path))

class VolumeRestoreDialog(ProcessDialog):

    def __init__(self, volume_path):
        ProcessDialog.__init__(self, 'journal-restore-volume', \
                              [volume_path, misc.get_backup_identifier()])

        self._resetup_information(volume_path)

    def _resetup_information(self, volume_path):
        self._start_message = '%s %s. \n\n' % (_('Please wait, restoring Journal content from'), volume_path) + \
                              '<big><b>%s</b></big>' % _('Do not remove the storage device!')

        self._finished_message = _('The Journal content has been restored.')

        self._title.set_markup('<big><b>%s</b></big>' % _('Restore'))

        self._message.set_markup('%s %s.\n\n' % (_('Journal content will be restored from'), volume_path) + \
                                 '<big><b>%s</b> %s</big>' % (_('Warning:'), _('Current Journal content will be deleted!')))

        self._prerequisite_message = _(', please close all the running activities.')

    def _check_prerequisites(self):
        return len(shell.get_model()) <= 1

class XSBackupDialog(ProcessDialog):

    def __init__(self, xs_hostname):
        ProcessDialog.__init__(self, 'journal-backup')
        self._resetup_information(xs_hostname)

    def _resetup_information(self, xs_hostname):
        self._start_message = '%s %s.' % (_('Please wait, saving Journal content to'), xs_hostname)

        self._finished_message = _('The journal content has been saved.')

        self._title.set_markup('<big><b>%s</b></big>' % _('Backup'))

        self._message.set_text('%s %s.' % (_('Journal content will be saved to'), xs_hostname))

class XSRestoreDialog(ProcessDialog):

    def __init__(self, xs_hostname):
        ProcessDialog.__init__(self, 'journal-restore')
        self._resetup_information(xs_hostname)

    def _resetup_information(self, xs_hostname):
        self._start_message = '%s %s.' % (_('Please wait, restoring journal content from'), xs_hostname)

        self._finished_message = _('The journal content has been restored.')

        self._title.set_markup('<big><b>%s</b></big>' % _('Restore'))

        self._message.set_text('%s %s.' % (_('Journal content will be restored from'), xs_hostname))

        self._prerequisite_message = _(', please close all the running activities.')

    def _check_prerequisites(self):
        return len(shell.get_model()) <= 1

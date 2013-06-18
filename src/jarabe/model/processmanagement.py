# Copyright (C) 2010, Paraguay Educa <tecnologia@paraguayeduca.org>
# Copyright (C) 2010, Plan Ceibal <comunidad@plan.ceibal.edu.uy>
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
import gobject
import glib
import gio

from sugar import env
from gettext import gettext as _

BYTES_TO_READ = 100

class ProcessManagement(gobject.GObject):

    __gtype_name__ = 'ProcessManagement'

    __gsignals__ = {
        'process-management-running'    : (gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE, ([str])),
        'process-management-started'    : (gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE, ([])),
        'process-management-finished'    : (gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE, ([])),
        'process-management-failed'    : (gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE, ([str]))
    }

    def __init__(self):
        gobject.GObject.__init__(self)
        self._running = False

    def do_process(self, cmd):
        self._run_cmd_async(cmd)

    def _report_process_status(self, stream, result):
        data = stream.read_finish(result)

        if len(data):
            self.emit('process-management-running', data)
            stream.read_async(BYTES_TO_READ, self._report_process_status)

    def _report_process_error(self, stream, result, concat_err=''):
        data = stream.read_finish(result)
        concat_err = concat_err + data

        if len(data) == 0:
                self.emit('process-management-failed', concat_err)
        else:
            stream.read_async(BYTES_TO_READ, self._report_process_error, user_data=concat_err)

    def _notify_error(self, stderr):
        stdin_stream = gio.unix.InputStream(stderr, True)
        stdin_stream.read_async(BYTES_TO_READ, self._report_process_error)

    def _notify_process_status(self, stdout):
        stdin_stream = gio.unix.InputStream(stdout, True)
        stdin_stream.read_async(BYTES_TO_READ, self._report_process_status)

    def _run_cmd_async(self, cmd):
        if self._running == False:
            try:
                pid, stdin, stdout, stderr = glib.spawn_async(cmd, flags=glib.SPAWN_DO_NOT_REAP_CHILD, standard_output=True, standard_error=True)
                gobject.child_watch_add(pid, _handle_process_end, (self, stderr))
            except Exception:
                self.emit('process-management-failed', _("Error - Call process: ") + str(cmd))
            else:
                self._notify_process_status(stdout)
                self._running  = True
                self.emit('process-management-started')

def _handle_process_end(pid, condition, (myself, stderr)):
    myself._running = False

    if os.WIFEXITED(condition) and\
        os.WEXITSTATUS(condition) == 0:
            myself.emit('process-management-finished')
    else:
        myself._notify_error(stderr)

def find_and_absolutize(script_name):
    paths = env.os.environ['PATH'].split(':')
    for path in paths:
        looking_path =  path + '/' + script_name
        if env.os.path.isfile(looking_path):
            return looking_path

    return None

# Copyright (C) 2008, OLPC
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
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301 USA

import gtk
import gobject
from gettext import gettext as _

from sugar.graphics import style

from jarabe.controlpanel.sectionview import SectionView
from jarabe.controlpanel.inlinealert import InlineAlert


CLASS = 'Network'
ICON = 'module-network'
TITLE = _('Network')

_APPLY_TIMEOUT = 3000


class Network(SectionView):
    def __init__(self, model, alerts):
        SectionView.__init__(self)

        self._model = model
        self.restart_alerts = alerts
        self._jabber_sid = 0
        self._jabber_valid = True
        self._radio_valid = True
        self._jabber_change_handler = None
        self._radio_change_handler = None
        self._network_configuration_reset_handler = None

        self.set_border_width(style.DEFAULT_SPACING * 2)
        self.set_spacing(style.DEFAULT_SPACING)
        group = gtk.SizeGroup(gtk.SIZE_GROUP_HORIZONTAL)

        self._radio_alert_box = gtk.HBox(spacing=style.DEFAULT_SPACING)
        self._jabber_alert_box = gtk.HBox(spacing=style.DEFAULT_SPACING)

        workspace = gtk.VBox()
        workspace.show()

        separator_wireless = gtk.HSeparator()
        workspace.pack_start(separator_wireless, expand=False)
        separator_wireless.show()

        label_wireless = gtk.Label(_('Wireless'))
        label_wireless.set_alignment(0, 0)
        workspace.pack_start(label_wireless, expand=False)
        label_wireless.show()
        box_wireless = gtk.VBox()
        box_wireless.set_border_width(style.DEFAULT_SPACING * 2)
        box_wireless.set_spacing(style.DEFAULT_SPACING)

        radio_info = gtk.Label(_('Turn off the wireless radio to save battery'
                                 ' life'))
        radio_info.set_alignment(0, 0)
        radio_info.set_line_wrap(True)
        radio_info.show()
        box_wireless.pack_start(radio_info, expand=False)

        box_radio = gtk.HBox(spacing=style.DEFAULT_SPACING)
        self._button = gtk.CheckButton()
        self._button.set_alignment(0, 0)
        box_radio.pack_start(self._button, expand=False)
        self._button.show()

        label_radio = gtk.Label(_('Radio'))
        label_radio.set_alignment(0, 0.5)
        box_radio.pack_start(label_radio, expand=False)
        label_radio.show()

        box_wireless.pack_start(box_radio, expand=False)
        box_radio.show()

        self._radio_alert = InlineAlert()
        self._radio_alert_box.pack_start(self._radio_alert, expand=False)
        box_radio.pack_end(self._radio_alert_box, expand=False)
        self._radio_alert_box.show()
        if 'radio' in self.restart_alerts:
            self._radio_alert.props.msg = self.restart_msg
            self._radio_alert.show()

        history_info = gtk.Label(_('Discard network history if you have'
                                   ' trouble connecting to the network'))
        history_info.set_alignment(0, 0)
        history_info.set_line_wrap(True)
        history_info.show()
        box_wireless.pack_start(history_info, expand=False)

        box_clear_history = gtk.HBox(spacing=style.DEFAULT_SPACING)
        self._clear_history_button = gtk.Button()
        self._clear_history_button.set_label(_('Discard network history'))
        box_clear_history.pack_start(self._clear_history_button, expand=False)
        if not self._model.have_networks():
            self._clear_history_button.set_sensitive(False)
        self._clear_history_button.show()
        box_wireless.pack_start(box_clear_history, expand=False)
        box_clear_history.show()

        workspace.pack_start(box_wireless, expand=False)
        box_wireless.show()

        separator_mesh = gtk.HSeparator()
        workspace.pack_start(separator_mesh, False)
        separator_mesh.show()

        label_mesh = gtk.Label(_('Collaboration'))
        label_mesh.set_alignment(0, 0)
        workspace.pack_start(label_mesh, expand=False)
        label_mesh.show()
        box_mesh = gtk.VBox()
        box_mesh.set_border_width(style.DEFAULT_SPACING * 2)
        box_mesh.set_spacing(style.DEFAULT_SPACING)

        server_info = gtk.Label(_("The server is the equivalent of what"
                                  " room you are in; people on the same server"
                                  " will be able to see each other, even when"
                                  " they aren't on the same network."))
        server_info.set_alignment(0, 0)
        server_info.set_line_wrap(True)
        box_mesh.pack_start(server_info, expand=False)
        server_info.show()

        box_server = gtk.HBox(spacing=style.DEFAULT_SPACING)
        label_server = gtk.Label(_('Server:'))
        label_server.set_alignment(1, 0.5)
        label_server.modify_fg(gtk.STATE_NORMAL,
                               style.COLOR_SELECTION_GREY.get_gdk_color())
        box_server.pack_start(label_server, expand=False)
        group.add_widget(label_server)
        label_server.show()
        self._entry = gtk.Entry()
        self._entry.set_alignment(0)
        self._entry.modify_bg(gtk.STATE_INSENSITIVE,
                        style.COLOR_WHITE.get_gdk_color())
        self._entry.modify_base(gtk.STATE_INSENSITIVE,
                          style.COLOR_WHITE.get_gdk_color())
        self._entry.set_size_request(int(gtk.gdk.screen_width() / 3), -1)
        box_server.pack_start(self._entry, expand=False)
        self._entry.show()
        box_mesh.pack_start(box_server, expand=False)
        box_server.show()

        self._jabber_alert = InlineAlert()
        label_jabber_error = gtk.Label()
        group.add_widget(label_jabber_error)
        self._jabber_alert_box.pack_start(label_jabber_error, expand=False)
        label_jabber_error.show()
        self._jabber_alert_box.pack_start(self._jabber_alert, expand=False)
        box_mesh.pack_end(self._jabber_alert_box, expand=False)
        self._jabber_alert_box.show()
        if 'jabber' in self.restart_alerts:
            self._jabber_alert.props.msg = self.restart_msg
            self._jabber_alert.show()

        workspace.pack_start(box_mesh, expand=False)
        box_mesh.show()

        scrolled = gtk.ScrolledWindow()
        scrolled.set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)
        scrolled.add_with_viewport(workspace)
        scrolled.show()
        self.add(scrolled)

        self.setup()

    def setup(self):
        self._entry.set_text(self._model.get_jabber())
        try:
            radio_state = self._model.get_radio()
        except self._model.ReadError, detail:
            self._radio_alert.props.msg = detail
            self._radio_alert.show()
        else:
            self._button.set_active(radio_state)

        self._jabber_valid = True
        self._radio_valid = True
        self.needs_restart = False
        self._radio_change_handler = self._button.connect( \
                'toggled', self.__radio_toggled_cb)
        self._jabber_change_handler = self._entry.connect( \
                'changed', self.__jabber_changed_cb)
        self._network_configuration_reset_handler =  \
                self._clear_history_button.connect( \
                        'clicked', self.__network_configuration_reset_cb)

    def undo(self):
        self._button.disconnect(self._radio_change_handler)
        self._entry.disconnect(self._jabber_change_handler)
        self._model.undo()
        self._jabber_alert.hide()
        self._radio_alert.hide()

    def _validate(self):
        if self._jabber_valid and self._radio_valid:
            self.props.is_valid = True
        else:
            self.props.is_valid = False

    def __radio_toggled_cb(self, widget, data=None):
        radio_state = widget.get_active()
        try:
            self._model.set_radio(radio_state)
        except self._model.ReadError, detail:
            self._radio_alert.props.msg = detail
            self._radio_valid = False
        else:
            self._radio_valid = True
            if self._model.have_networks():
                self._clear_history_button.set_sensitive(True)

        self._validate()
        return False

    def __jabber_changed_cb(self, widget, data=None):
        if self._jabber_sid:
            gobject.source_remove(self._jabber_sid)
        self._jabber_sid = gobject.timeout_add(_APPLY_TIMEOUT,
                                               self.__jabber_timeout_cb,
                                               widget)

    def __jabber_timeout_cb(self, widget):
        self._jabber_sid = 0
        if widget.get_text() == self._model.get_jabber:
            return
        try:
            self._model.set_jabber(widget.get_text())
        except self._model.ReadError, detail:
            self._jabber_alert.props.msg = detail
            self._jabber_valid = False
            self._jabber_alert.show()
            self.restart_alerts.append('jabber')
        else:
            self._jabber_valid = True
            self._jabber_alert.hide()

        self._validate()
        return False

    def __network_configuration_reset_cb(self, widget):
        # FIXME: takes effect immediately, not after CP is closed with
        # confirmation button
        self._model.clear_networks()
        if not self._model.have_networks():
            self._clear_history_button.set_sensitive(False)

# Copyright (C) 2006-2008 Red Hat, Inc.
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

import gconf

from sugar import env
from sugar import _sugarext
from sugar import dispatch


VOLUME_STEP = 10

muted_changed = dispatch.Signal()
volume_changed = dispatch.Signal()

_volume = _sugarext.VolumeAlsa()


def get_muted():
    return _volume.get_mute()


def get_volume():
    return _volume.get_volume()


def set_volume(new_volume):
    old_volume = _volume.get_volume()
    _volume.set_volume(new_volume)

    volume_changed.send(None)
    save()


def set_muted(new_state):
    old_state = _volume.get_mute()
    _volume.set_mute(new_state)

    muted_changed.send(None)
    save()


def save():
    if env.is_emulator() is False:
        client = gconf.client_get_default()
        client.set_int('/desktop/sugar/sound/volume', get_volume())


def restore():
    if env.is_emulator() is False:
        client = gconf.client_get_default()
        set_volume(client.get_int('/desktop/sugar/sound/volume'))

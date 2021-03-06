# Copyright (C) 2007-2011, One Laptop per Child
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
import os
import errno
import subprocess
from datetime import datetime
import time
import shutil
import tempfile
from stat import S_IFLNK, S_IFMT, S_IFDIR, S_IFREG
import re
from operator import itemgetter
import simplejson
from gettext import gettext as _

import gobject
import dbus
import gio
import gconf

from sugar import dispatch
from sugar import mime
from sugar import util


DS_DBUS_SERVICE = 'org.laptop.sugar.DataStore'
DS_DBUS_INTERFACE = 'org.laptop.sugar.DataStore'
DS_DBUS_PATH = '/org/laptop/sugar/DataStore'

# Properties the journal cares about.
PROPERTIES = ['activity', 'activity_id', 'buddies', 'bundle_id',
              'creation_time', 'filesize', 'icon-color', 'keep', 'mime_type',
              'mountpoint', 'mtime', 'progress', 'timestamp', 'title', 'uid']

MIN_PAGES_TO_CACHE = 3
MAX_PAGES_TO_CACHE = 5

JOURNAL_METADATA_DIR = '.Sugar-Metadata'

_datastore = None
created = dispatch.Signal()
updated = dispatch.Signal()
deleted = dispatch.Signal()

_sync_signals_enabled = True
def _emit_created(object_id):
    global _sync_signals_enabled
    if _sync_signals_enabled:
        created.send(None, object_id=object_id)

def _emit_deleted(object_id):
    global _sync_signals_enabled
    if _sync_signals_enabled:
        deleted.send(None, object_id=object_id)

class _Cache(object):

    __gtype_name__ = 'model_Cache'

    def __init__(self, entries=None):
        self._array = []
        if entries is not None:
            self.append_all(entries)

    def prepend_all(self, entries):
        self._array[0:0] = entries

    def append_all(self, entries):
        self._array += entries

    def __len__(self):
        return len(self._array)

    def __getitem__(self, key):
        return self._array[key]

    def __delitem__(self, key):
        del self._array[key]


class BaseResultSet(object):
    """Encapsulates the result of a query
    """

    def __init__(self, query, page_size):
        self._total_count = -1
        self._position = -1
        self._query = query
        self._page_size = page_size

        self._offset = 0
        self._cache = _Cache()

        self.ready = dispatch.Signal()
        self.progress = dispatch.Signal()

    def setup(self):
        self.ready.send(self)

    def stop(self):
        pass

    def get_length(self):
        if self._total_count == -1:
            query = self._query.copy()
            query['limit'] = self._page_size * MIN_PAGES_TO_CACHE
            entries, self._total_count = self.find(query)
            self._cache.append_all(entries)
            self._offset = 0
        return self._total_count

    length = property(get_length)

    def find(self, query):
        raise NotImplementedError()

    def seek(self, position):
        self._position = position

    def read(self):
        if self._position == -1:
            self.seek(0)

        if self._position < self._offset:
            remaining_forward_entries = 0
        else:
            remaining_forward_entries = self._offset + len(self._cache) - \
                                        self._position

        if self._position > self._offset + len(self._cache):
            remaining_backwards_entries = 0
        else:
            remaining_backwards_entries = self._position - self._offset

        last_cached_entry = self._offset + len(self._cache)

        if remaining_forward_entries <= 0 and remaining_backwards_entries <= 0:

            # Total cache miss: remake it
            limit = self._page_size * MIN_PAGES_TO_CACHE
            offset = max(0, self._position - limit / 2)
            logging.debug('remaking cache, offset: %r limit: %r', offset,
                limit)
            query = self._query.copy()
            query['limit'] = limit
            query['offset'] = offset
            entries, self._total_count = self.find(query)

            del self._cache[:]
            self._cache.append_all(entries)
            self._offset = offset

        elif (remaining_forward_entries <= 0 and
              remaining_backwards_entries > 0):

            # Add one page to the end of cache
            logging.debug('appending one more page, offset: %r',
                last_cached_entry)
            query = self._query.copy()
            query['limit'] = self._page_size
            query['offset'] = last_cached_entry
            entries, self._total_count = self.find(query)

            # update cache
            self._cache.append_all(entries)

            # apply the cache limit
            cache_limit = self._page_size * MAX_PAGES_TO_CACHE
            objects_excess = len(self._cache) - cache_limit
            if objects_excess > 0:
                self._offset += objects_excess
                del self._cache[:objects_excess]

        elif remaining_forward_entries > 0 and \
                remaining_backwards_entries <= 0 and self._offset > 0:

            # Add one page to the beginning of cache
            limit = min(self._offset, self._page_size)
            self._offset = max(0, self._offset - limit)

            logging.debug('prepending one more page, offset: %r limit: %r',
                self._offset, limit)
            query = self._query.copy()
            query['limit'] = limit
            query['offset'] = self._offset
            entries, self._total_count = self.find(query)

            # update cache
            self._cache.prepend_all(entries)

            # apply the cache limit
            cache_limit = self._page_size * MAX_PAGES_TO_CACHE
            objects_excess = len(self._cache) - cache_limit
            if objects_excess > 0:
                del self._cache[-objects_excess:]

        return self._cache[self._position - self._offset]


class DatastoreResultSet(BaseResultSet):
    """Encapsulates the result of a query on the datastore
    """
    def __init__(self, query, page_size):

        if query.get('query', '') and not query['query'].startswith('"'):
            query_text = ''
            words = query['query'].split(' ')
            for word in words:
                if word:
                    if query_text:
                        query_text += ' '
                    query_text += word + '*'

            query['query'] = query_text

        BaseResultSet.__init__(self, query, page_size)

    def find(self, query):
        entries, total_count = _get_datastore().find(query, PROPERTIES,
                                                     byte_arrays=True)

        for entry in entries:
            entry['mountpoint'] = '/'

        return entries, total_count


class InplaceResultSet(BaseResultSet):
    """Encapsulates the result of a query on a mount point
    """
    def __init__(self, query, page_size, mount_point):
        BaseResultSet.__init__(self, query, page_size)
        self._mount_point = mount_point
        self._file_list = None
        self._pending_directories = []
        self._visited_directories = []
        self._pending_files = []
        self._stopped = False

        query_text = query.get('query', '')
        if query_text.startswith('"') and query_text.endswith('"'):
            self._regex = re.compile('*%s*' % query_text.strip(['"']))
        elif query_text:
            expression = ''
            for word in query_text.split(' '):
                expression += '(?=.*%s.*)' % word
            self._regex = re.compile(expression, re.IGNORECASE)
        else:
            self._regex = None

        if query.get('timestamp', ''):
            self._date_start = int(query['timestamp']['start'])
            self._date_end = int(query['timestamp']['end'])
        else:
            self._date_start = None
            self._date_end = None

        self._mime_types = query.get('mime_type', [])

        self._sort = query.get('order_by', ['+timestamp'])[0]

    def setup(self):
        self._file_list = []
        self._pending_directories = [self._mount_point]
        self._visited_directories = []
        self._pending_files = []
        gobject.idle_add(self._scan)

    def stop(self):
        self._stopped = True

    def setup_ready(self):
        if self._sort[1:] == 'filesize':
            keygetter = itemgetter(3)
        else:
            # timestamp
            keygetter = itemgetter(2)
        self._file_list.sort(lambda a, b: cmp(b, a),
                             key=keygetter,
                             reverse=(self._sort[0] == '-'))
        self.ready.send(self)

    def find(self, query):
        if self._file_list is None:
            raise ValueError('Need to call setup() first')

        if self._stopped:
            raise ValueError('InplaceResultSet already stopped')

        t = time.time()

        offset = int(query.get('offset', 0))
        limit = int(query.get('limit', len(self._file_list)))
        total_count = len(self._file_list)

        files = self._file_list[offset:offset + limit]

        entries = []
        for file_path, stat, mtime_, size_, metadata in files:
            if metadata is None:
                metadata = _get_file_metadata(file_path, stat)
            metadata['mountpoint'] = self._mount_point
            entries.append(metadata)

        logging.debug('InplaceResultSet.find took %f s.', time.time() - t)

        return entries, total_count

    def _scan(self):
        if self._stopped:
            return False

        self.progress.send(self)

        if self._pending_files:
            self._scan_a_file()
            return True

        if self._pending_directories:
            self._scan_a_directory()
            return True

        self.setup_ready()
        self._visited_directories = []
        return False

    def _scan_a_file(self):
        full_path = self._pending_files.pop(0)
        metadata = None

        try:
            stat = os.lstat(full_path)
        except OSError, e:
            if e.errno != errno.ENOENT:
                logging.exception(
                    'Error reading metadata of file %r', full_path)
            return

        if S_IFMT(stat.st_mode) == S_IFLNK:
            try:
                link = os.readlink(full_path)
            except OSError, e:
                logging.exception(
                    'Error reading target of link %r', full_path)
                return

            if not os.path.abspath(link).startswith(self._mount_point):
                return

            try:
                stat = os.stat(full_path)

            except OSError, e:
                if e.errno != errno.ENOENT:
                    logging.exception(
                        'Error reading metadata of linked file %r', full_path)
                return

        if S_IFMT(stat.st_mode) == S_IFDIR:
            id_tuple = stat.st_ino, stat.st_dev
            if not id_tuple in self._visited_directories:
                self._visited_directories.append(id_tuple)
                self._pending_directories.append(full_path)
            return

        if S_IFMT(stat.st_mode) != S_IFREG:
            return

        if self._regex is not None and \
                not self._regex.match(full_path):
            metadata = _get_file_metadata(full_path, stat,
                                          fetch_preview=False)
            if not metadata:
                return
            add_to_list = False
            for f in ['fulltext', 'title',
                      'description', 'tags']:
                if f in metadata and \
                        self._regex.match(metadata[f]):
                    add_to_list = True
                    break
            if not add_to_list:
                return

        if self._date_start is not None and stat.st_mtime < self._date_start:
            return

        if self._date_end is not None and stat.st_mtime > self._date_end:
            return

        if self._mime_types:
            mime_type = gio.content_type_guess(filename=full_path)
            if mime_type not in self._mime_types:
                return

        file_info = (full_path, stat, int(stat.st_mtime), stat.st_size,
                     metadata)
        self._file_list.append(file_info)

        return

    def _scan_a_directory(self):
        dir_path = self._pending_directories.pop(0)

        try:
            entries = os.listdir(dir_path)
        except OSError, e:
            if e.errno != errno.EACCES:
                logging.exception('Error reading directory %r', dir_path)
            return

        for entry in entries:
            if entry.startswith('.'):
                continue
            self._pending_files.append(dir_path + '/' + entry)
        return

def _set_signals_state(state, callback=None, data=None):
    global _sync_signals_enabled
    _sync_signals_enabled = state
    if callback:
        callback(data)

def copy_entries(entries_set, mount_point):
    _set_signals_state(False)
    status, message = True, ''
    for entry_uid  in entries_set:
        try:
            metadata = get(entry_uid)
            copy(metadata, mount_point)
        except ValueError:
            logging.warning('Entry %s has nothing to copied', entry_uid)
        except (OSError, IOError):
            status, message = False, _('No available space to continue')
            break
    gobject.idle_add(_set_signals_state, True)
    return (status, message)

def delete_entries(entries_set, mount_point):
    _set_signals_state(False)
    for entry_uid in entries_set:
        try:
            delete(entry_uid)
        except (OSError, IOError):
            logging.warning('Entry %s could not be deleted', entry_uid)
    gobject.idle_add(_set_signals_state, True,
                     __post_delete_entries_cb, mount_point)

def __post_delete_entries_cb(mount_point):
    if mount_point is '/':
        mount_point = 'abcde'
    _emit_deleted(mount_point)



def _get_file_metadata(path, stat, fetch_preview=True):
    """Return the metadata from the corresponding file.

    Reads the metadata stored in the json file or create the
    metadata based on the file properties.

    """
    filename = os.path.basename(path)
    dir_path = os.path.dirname(path)
    metadata = _get_file_metadata_from_json(dir_path, filename, fetch_preview)
    if metadata:
        if 'filesize' not in metadata:
            metadata['filesize'] = stat.st_size
        return metadata

    return {'uid': path,
            'title': os.path.basename(path),
            'timestamp': stat.st_mtime,
            'filesize': stat.st_size,
            'mime_type': gio.content_type_guess(filename=path),
            'activity': '',
            'activity_id': '',
            'icon-color': '#000000,#ffffff',
            'description': path}


def _get_file_metadata_from_json(dir_path, filename, fetch_preview):
    """Read the metadata from the json file and the preview
    stored on the external device.

    If the metadata is corrupted we do remove it and the preview as well.

    """
    metadata = None
    metadata_path = os.path.join(dir_path, JOURNAL_METADATA_DIR,
                                 filename + '.metadata')
    preview_path = os.path.join(dir_path, JOURNAL_METADATA_DIR,
                                filename + '.preview')

    if not os.path.exists(metadata_path):
        return None

    try:
        metadata = simplejson.load(open(metadata_path))
    except (ValueError, EnvironmentError):
        os.unlink(metadata_path)
        if os.path.exists(preview_path):
            os.unlink(preview_path)
        logging.error('Could not read metadata for file %r on '
                      'external device.', filename)
        return None
    else:
        metadata['uid'] = os.path.join(dir_path, filename)

    if not fetch_preview:
        if 'preview' in metadata:
            del(metadata['preview'])
    else:
        if os.path.exists(preview_path):
            try:
                metadata['preview'] = dbus.ByteArray(open(preview_path).read())
            except EnvironmentError:
                logging.debug('Could not read preview for file %r on '
                              'external device.', filename)

    return metadata


def _get_datastore():
    global _datastore
    if _datastore is None:
        bus = dbus.SessionBus()
        remote_object = bus.get_object(DS_DBUS_SERVICE, DS_DBUS_PATH)
        _datastore = dbus.Interface(remote_object, DS_DBUS_INTERFACE)

        _datastore.connect_to_signal('Created', _datastore_created_cb)
        _datastore.connect_to_signal('Updated', _datastore_updated_cb)
        _datastore.connect_to_signal('Deleted', _datastore_deleted_cb)

    return _datastore


def _datastore_created_cb(object_id):
    _emit_created(object_id)

def _datastore_updated_cb(object_id):
    updated.send(None, object_id=object_id)


def _datastore_deleted_cb(object_id):
    _emit_deleted(object_id)

def find(query_, page_size):
    """Returns a ResultSet
    """
    query = query_.copy()

    mount_points = query.pop('mountpoints', ['/'])
    if mount_points is None or len(mount_points) != 1:
        raise ValueError('Exactly one mount point must be specified')

    if mount_points[0] == '/':
        return DatastoreResultSet(query, page_size)
    else:
        return InplaceResultSet(query, page_size, mount_points[0])


def _get_mount_point(path):
    dir_path = os.path.dirname(path)
    while dir_path:
        if os.path.ismount(dir_path):
            return dir_path
        else:
            dir_path = dir_path.rsplit(os.sep, 1)[0]
    return None


def get(object_id):
    """Returns the metadata for an object
    """
    if os.path.exists(object_id):
        stat = os.stat(object_id)
        metadata = _get_file_metadata(object_id, stat)
        metadata['mountpoint'] = _get_mount_point(object_id)
    else:
        metadata = _get_datastore().get_properties(object_id, byte_arrays=True)
        metadata['mountpoint'] = '/'
    return metadata


def get_file(object_id):
    """Returns the file for an object
    """
    if os.path.exists(object_id):
        logging.debug('get_file asked for file with path %r', object_id)
        return object_id
    else:
        logging.debug('get_file asked for entry with id %r', object_id)
        file_path = _get_datastore().get_filename(object_id)
        if file_path:
            return util.TempFilePath(file_path)
        else:
            return None


def get_file_size(object_id):
    """Return the file size for an object
    """
    logging.debug('get_file_size %r', object_id)
    if os.path.exists(object_id):
        return os.stat(object_id).st_size

    file_path = _get_datastore().get_filename(object_id)
    if file_path:
        size = os.stat(file_path).st_size
        os.remove(file_path)
        return size

    return 0


def get_unique_values(key):
    """Returns a list with the different values a property has taken
    """
    empty_dict = dbus.Dictionary({}, signature='ss')
    return _get_datastore().get_uniquevaluesfor(key, empty_dict)


def delete(object_id):
    """Removes an object from persistent storage
    """
    if not os.path.exists(object_id):
        _get_datastore().delete(object_id)
    else:
        os.unlink(object_id)
        dir_path = os.path.dirname(object_id)
        filename = os.path.basename(object_id)
        old_files = [os.path.join(dir_path, JOURNAL_METADATA_DIR,
                                  filename + '.metadata'),
                     os.path.join(dir_path, JOURNAL_METADATA_DIR,
                                  filename + '.preview')]
        for old_file in old_files:
            if os.path.exists(old_file):
                try:
                    os.unlink(old_file)
                except EnvironmentError:
                    logging.error('Could not remove metadata=%s '
                                  'for file=%s', old_file, filename)
        _emit_deleted(object_id)


def copy(metadata, mount_point):
    """Copies an object to another mount point
    """
    metadata = get(metadata['uid'])
    if mount_point == '/' and metadata['icon-color'] == '#000000,#ffffff':
        client = gconf.client_get_default()
        metadata['icon-color'] = client.get_string('/desktop/sugar/user/color')
    file_path = get_file(metadata['uid'])
    if file_path is None:
        file_path = ''

    metadata['mountpoint'] = mount_point
    del metadata['uid']

    return write(metadata, file_path, transfer_ownership=False)


def write(metadata, file_path='', update_mtime=True, transfer_ownership=True):
    """Creates or updates an entry for that id
    """
    logging.debug('model.write %r %r %r', metadata.get('uid', ''), file_path,
        update_mtime)
    if update_mtime:
        metadata['mtime'] = datetime.now().isoformat()
        metadata['timestamp'] = int(time.time())

    if metadata.get('mountpoint', '/') == '/':
        if metadata.get('uid', ''):
            object_id = _get_datastore().update(metadata['uid'],
                                                 dbus.Dictionary(metadata),
                                                 file_path,
                                                 transfer_ownership)
        else:
            object_id = _get_datastore().create(dbus.Dictionary(metadata),
                                                 file_path,
                                                 transfer_ownership)
    else:
        object_id = _write_entry_on_external_device(metadata, file_path)

    return object_id


def _rename_entry_on_external_device(file_path, destination_path,
                                     metadata_dir_path):
    """Rename an entry with the associated metadata on an external device."""
    old_file_path = file_path
    if old_file_path != destination_path:
        os.rename(file_path, destination_path)
        old_fname = os.path.basename(file_path)
        old_files = [os.path.join(metadata_dir_path,
                                  old_fname + '.metadata'),
                     os.path.join(metadata_dir_path,
                                  old_fname + '.preview')]
        for ofile in old_files:
            if os.path.exists(ofile):
                try:
                    os.unlink(ofile)
                except EnvironmentError:
                    logging.error('Could not remove metadata=%s '
                                  'for file=%s', ofile, old_fname)


def _write_entry_on_external_device(metadata, file_path):
    """Create and update an entry copied from the
    DS to an external storage device.

    Besides copying the associated file a file for the preview
    and one for the metadata are stored in the hidden directory
    .Sugar-Metadata.

    This function handles renames of an entry on the
    external device and avoids name collisions. Renames are
    handled failsafe.

    """
    if 'uid' in metadata and os.path.exists(metadata['uid']):
        file_path = metadata['uid']

    if not file_path or not os.path.exists(file_path):
        raise ValueError('Entries without a file cannot be copied to '
                         'removable devices')

    if not metadata.get('title'):
        metadata['title'] = _('Untitled')
    file_name = get_file_name(metadata['title'], metadata['mime_type'])

    destination_path = os.path.join(metadata['mountpoint'], file_name)
    if destination_path != file_path:
        file_name = get_unique_file_name(metadata['mountpoint'], file_name)
        destination_path = os.path.join(metadata['mountpoint'], file_name)
        clean_name, extension_ = os.path.splitext(file_name)
        metadata['title'] = clean_name

    metadata_copy = metadata.copy()
    metadata_copy.pop('mountpoint', None)
    metadata_copy.pop('uid', None)
    metadata_copy.pop('filesize', None)

    metadata_dir_path = os.path.join(metadata['mountpoint'],
                                     JOURNAL_METADATA_DIR)
    if not os.path.exists(metadata_dir_path):
        os.mkdir(metadata_dir_path)

    preview = None
    if 'preview' in metadata_copy:
        preview = metadata_copy['preview']
        preview_fname = file_name + '.preview'
        metadata_copy.pop('preview', None)

    try:
        metadata_json = simplejson.dumps(metadata_copy)
    except (UnicodeDecodeError, EnvironmentError):
        logging.error('Could not convert metadata to json.')
    else:
        (fh, fn) = tempfile.mkstemp(dir=metadata['mountpoint'])
        os.write(fh, metadata_json)
        os.close(fh)
        os.rename(fn, os.path.join(metadata_dir_path, file_name + '.metadata'))

        if preview:
            (fh, fn) = tempfile.mkstemp(dir=metadata['mountpoint'])
            os.write(fh, preview)
            os.close(fh)
            os.rename(fn, os.path.join(metadata_dir_path, preview_fname))

    if not os.path.dirname(destination_path) == os.path.dirname(file_path):
        shutil.copy(file_path, destination_path)
    else:
        _rename_entry_on_external_device(file_path, destination_path,
                                         metadata_dir_path)

    object_id = destination_path
    _emit_created(object_id)

    return object_id


def get_file_name(title, mime_type):
    file_name = title

    extension = mime.get_primary_extension(mime_type)
    if extension is not None and extension:
        extension = '.' + extension
        if not file_name.endswith(extension):
            file_name += extension

    # Invalid characters in VFAT filenames. From
    # http://en.wikipedia.org/wiki/File_Allocation_Table
    invalid_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|', '\x7F']
    invalid_chars.extend([chr(x) for x in range(0, 32)])
    for char in invalid_chars:
        file_name = file_name.replace(char, '_')

    # FAT limit is 255, leave some space for uniqueness
    max_len = 250
    if len(file_name) > max_len:
        name, extension = os.path.splitext(file_name)
        file_name = name[0:max_len - len(extension)] + extension

    return file_name


def get_unique_file_name(mount_point, file_name):
    if os.path.exists(os.path.join(mount_point, file_name)):
        i = 1
        name, extension = os.path.splitext(file_name)
        while len(file_name) <= 255:
            file_name = name + '_' + str(i) + extension
            if not os.path.exists(os.path.join(mount_point, file_name)):
                break
            i += 1

    return file_name


def is_editable(metadata):
    if metadata.get('mountpoint', '/') == '/':
        return True
    else:
        return os.access(metadata['mountpoint'], os.W_OK)


def get_documents_path():
    """Gets the path of the DOCUMENTS folder

    If xdg-user-dir can not find the DOCUMENTS folder it returns
    $HOME, which we omit. xdg-user-dir handles localization
    (i.e. translation) of the filenames.

    Returns: Path to $HOME/DOCUMENTS or None if an error occurs
    """
    try:
        pipe = subprocess.Popen(['xdg-user-dir', 'DOCUMENTS'],
                                stdout=subprocess.PIPE)
        documents_path = os.path.normpath(pipe.communicate()[0].strip())
        if os.path.exists(documents_path) and \
                os.environ.get('HOME') != documents_path:
            return documents_path
    except OSError, exception:
        if exception.errno != errno.ENOENT:
            logging.exception('Could not run xdg-user-dir')
    return None

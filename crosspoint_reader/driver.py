import os
import time
import urllib.error
import urllib.parse
import urllib.request

from calibre.devices.errors import ControlError
from calibre.devices.interface import DevicePlugin
from calibre.devices.usbms.deviceconfig import DeviceConfig
from calibre.devices.usbms.books import Book, BookList
from calibre.ebooks.metadata.book.base import Metadata
from calibre.ptempfile import PersistentTemporaryFile

from . import ws_client
from .config import CrossPointConfigWidget, PREFS
from .converter import EpubConverter
from .log import add_log, add_error, add_warning, add_info, add_debug


class CrossPointDevice(DeviceConfig, DevicePlugin):
    name = 'CrossPoint Reader'
    gui_name = 'CrossPoint Reader'
    description = 'CrossPoint Reader wireless device with EPUB image conversion'
    supported_platforms = ['windows', 'osx', 'linux']
    author = 'CrossPoint Reader'
    version = (0, 2, 5)

    # Invalid USB vendor info to avoid USB scans matching.
    VENDOR_ID = [0xFFFF]
    PRODUCT_ID = [0xFFFF]
    BCD = [0xFFFF]

    FORMATS = ['epub']
    ALL_FORMATS = ['epub']
    SUPPORTS_SUB_DIRS = True
    MUST_READ_METADATA = False
    MANAGES_DEVICE_PRESENCE = True
    DEVICE_PLUGBOARD_NAME = 'CROSSPOINT_READER'
    MUST_READ_METADATA = False
    SUPPORTS_DEVICE_DB = False
    # Disable Calibre's device cache so we always refresh from device.
    device_is_usb_mass_storage = False

    def __init__(self, path):
        super().__init__(path)
        self.is_connected = False
        self.device_host = None
        self.device_port = None
        self.last_discovery = 0.0
        self.report_progress = lambda x, y: x
        self._debug_enabled = False

    def _log(self, message, level='info'):
        """Log a message with optional level filtering."""
        add_log(message)
        if self._debug_enabled:
            try:
                self.report_progress(0.0, message)
            except Exception:
                pass

    # Device discovery / presence
    def _discover(self):
        now = time.time()
        if now - self.last_discovery < 2.0:
            return None, None
        self.last_discovery = now
        host, port = ws_client.discover_device(
            timeout=1.0,
            debug=PREFS['debug'],
            logger=self._log,
            extra_hosts=[PREFS['host']],
        )
        if host and port:
            return host, port
        return None, None

    def detect_managed_devices(self, devices_on_system, force_refresh=False):
        if self.is_connected:
            return self
        debug = PREFS['debug']
        self._debug_enabled = debug
        if debug:
            self._log('[CrossPoint] detect_managed_devices')
        host, port = self._discover()
        if host:
            if debug:
                self._log(f'[CrossPoint] discovered {host} {port}')
            self.device_host = host
            self.device_port = port
            self.is_connected = True
            return self
        if debug:
            self._log('[CrossPoint] discovery failed')
        return None

    def open(self, connected_device, library_uuid):
        if not self.is_connected:
            raise ControlError(desc='Attempt to open a closed device')
        return True

    def get_device_information(self, end_session=True):
        host = self.device_host or PREFS['host']
        device_info = {
            'device_store_uuid': 'crosspoint-' + host.replace('.', '-'),
            'device_name': 'CrossPoint Reader',
            'device_version': '1',
        }

        # Try to get firmware version from /api/status endpoint
        try:
            status = self._http_get_json('/api/status', timeout=3)
            if status and 'version' in status:
                firmware_version = status['version']
                device_info['firmware_version'] = firmware_version
                self._log(f'[CrossPoint] Device firmware version: {firmware_version}')
            if status and 'mode' in status:
                self._log(f'[CrossPoint] Device WiFi mode: {status["mode"]}')
        except Exception as exc:
            self._log(f'[CrossPoint] Could not get device status: {exc}')

        return (self.gui_name, '1', '1', '', {'main': device_info})

    def reset(self, key='-1', log_packets=False, report_progress=None, detected_device=None):
        self.set_progress_reporter(report_progress)

    def set_progress_reporter(self, report_progress):
        if report_progress is None:
            self.report_progress = lambda x, y: x
        else:
            self.report_progress = report_progress

    def _http_base(self):
        host = self.device_host or PREFS['host']
        return f'http://{host}'

    def _http_get_json(self, path, params=None, timeout=5):
        url = self._http_base() + path
        if params:
            url += '?' + urllib.parse.urlencode(params)
        try:
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                data = resp.read().decode('utf-8', 'ignore')
        except Exception as exc:
            raise ControlError(desc=f'HTTP request failed: {exc}')
        try:
            import json
            return json.loads(data)
        except Exception as exc:
            raise ControlError(desc=f'Invalid JSON response: {exc}')

    def _http_post_form(self, path, data, timeout=5):
        url = self._http_base() + path
        body = urllib.parse.urlencode(data).encode('utf-8')
        req = urllib.request.Request(url, data=body, method='POST')
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status, resp.read().decode('utf-8', 'ignore')
        except Exception as exc:
            raise ControlError(desc=f'HTTP request failed: {exc}')

    def config_widget(self):
        return CrossPointConfigWidget()

    def save_settings(self, config_widget):
        config_widget.save()

    def _list_files_recursive(self, path='/'):
        """Return a flat list of (lpath, size) for all EPUB files on device."""
        results = []
        try:
            entries = self._http_get_json('/api/files', params={'path': path})
            self._log(f'[CrossPoint] _list_files_recursive: {path} got {len(entries)} entries')
        except Exception as exc:
            self._log(f'[CrossPoint] listing {path} failed: {exc}')
            return results
        for entry in entries:
            name = entry.get('name', '')
            if not name:
                continue
            if path == '/':
                entry_path = '/' + name
            else:
                entry_path = path + '/' + name

            # Log entry for debug
            self._log(f'[CrossPoint] entry: {entry_path} dir={entry.get("isDirectory")} epub={entry.get("isEpub")}')

            if entry.get('isDirectory'):
                results.extend(self._list_files_recursive(entry_path))
            # Check both isEpub flag and file extension
            elif entry.get('isEpub') or name.lower().endswith('.epub'):
                results.append((entry_path, entry.get('size', 0)))
        return results

    def books(self, oncard=None, end_session=True):
        if oncard is not None:
            return BookList(None, None, None)

        self._log('[CrossPoint] books: listing files from device...')
        file_list = self._list_files_recursive('/')
        self._log(f'[CrossPoint] books: found {len(file_list)} EPUB file(s)')

        bl = BookList(None, None, None)
        fetch_metadata = PREFS['fetch_metadata']
        for i, (lpath, size) in enumerate(file_list):
            title = os.path.splitext(os.path.basename(lpath))[0]
            meta = Metadata(title, [])
            if fetch_metadata:
                try:
                    self._log(f'[CrossPoint] [{i+1}/{len(file_list)}] Fetching metadata for {lpath}...')
                    from calibre.customize.ui import quick_metadata
                    from calibre.ebooks.metadata.meta import get_metadata
                    with self._download_temp(lpath) as tf:
                        with quick_metadata:
                            m = get_metadata(tf, stream_type='epub', force_read_metadata=True)
                        if m is not None:
                            meta = m
                            self._log(f'[CrossPoint] [{i+1}/{len(file_list)}] Metadata: {m.title}')
                except Exception as exc:
                    self._log(f'[CrossPoint] metadata read failed for {lpath}: {exc}')
            book = Book('', lpath, size=size, other=meta)
            bl.add_book(book, replace_metadata=True)

        self._log(f'[CrossPoint] books: returning {len(bl)} book(s)')
        return bl

    def sync_booklists(self, booklists, end_session=True):
        # No on-device metadata sync supported.
        return None

    def card_prefix(self, end_session=True):
        return None, None

    def total_space(self, end_session=True):
        return 10 * 1024 * 1024 * 1024, 0, 0

    def free_space(self, end_session=True):
        return 10 * 1024 * 1024 * 1024, 0, 0

    def _format_upload_path(self, mi, original_name):
        """Format an upload path using the send-to-device template.

        Returns (subdirs, filename) where subdirs is a list of directory
        components from the template (may be empty for flat templates).
        """
        try:
            from calibre.library.save_to_disk import config as sconfig, get_components
            from calibre.utils.filenames import ascii_filename

            template = self.save_template()
            if not template:
                template = sconfig().parse().send_template

            components = get_components(
                template, mi, -1, '%b %Y', 250,
                ascii_filename, to_lowercase=False,
                replace_whitespace=False, safe_format=True,
                last_has_extension=False,
            )

            components = [c.strip() for c in components if c and c.strip()]
            if not components:
                return [], original_name

            ext = os.path.splitext(original_name)[1]
            filename = components[-1] + ext
            subdirs = components[:-1]
            return subdirs, filename
        except Exception as exc:
            self._log(f'[CrossPoint] template format failed: {exc}')
            return [], original_name

    def _mkdir_on_device(self, name, path):
        """Create a directory on device via POST /mkdir.

        Silently ignores 400 errors (folder already exists).
        Uses urllib directly to avoid _http_post_form which wraps all
        errors as ControlError.
        """
        url = self._http_base() + '/mkdir'
        body = urllib.parse.urlencode({'name': name, 'path': path}).encode('utf-8')
        req = urllib.request.Request(url, data=body, method='POST')
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 400:
                self._log(f'[CrossPoint] mkdir ignored (already exists): {name} in {path}')
            else:
                raise ControlError(desc=f'mkdir failed for {name} in {path}: {exc}')
        except Exception as exc:
            raise ControlError(desc=f'mkdir failed for {name} in {path}: {exc}')

    def _ensure_dir(self, parent_path, subdirs):
        """Ensure subdirectories exist under parent_path on device.

        Creates the full nested path with a single mkdir call (device
        uses recursive mkdir). Returns the full directory path.
        """
        subdir_path = '/'.join(subdirs)
        self._mkdir_on_device(subdir_path, parent_path)
        if parent_path == '/':
            return '/' + subdir_path
        return parent_path + '/' + subdir_path

    def _convert_epub(self, input_path):
        """Convert EPUB images to baseline JPEG format.
        
        Returns path to converted file (may be a temp file).
        """
        if not PREFS['enable_conversion']:
            return input_path
        
        temp_path = None
        try:
            # Create converter with settings from preferences
            converter = EpubConverter(
                jpeg_quality=PREFS['jpeg_quality'],
                max_width=PREFS['screen_width'],
                max_height=PREFS['screen_height'],
                enable_split_rotate=PREFS['light_novel_mode'],
                overlap=PREFS['split_overlap'] / 100.0,
                logger=self._log,
            )
            
            # Create temp file for converted EPUB
            temp_file = PersistentTemporaryFile(suffix='_baseline.epub')
            temp_path = temp_file.name
            temp_file.close()
            
            # Convert
            self._log(f'[CrossPoint] Converting: {os.path.basename(input_path)}')
            converter.convert_epub(input_path, temp_path)
            
            return temp_path
            
        except Exception as exc:
            self._log(f'[CrossPoint] Conversion failed: {exc}')
            # Clean up temp file on failure
            if temp_path:
                try:
                    os.remove(temp_path)
                except Exception as cleanup_err:
                    self._log(f'[CrossPoint] Failed to clean up temp file {temp_path}: {cleanup_err}')
            # Return original file if conversion fails
            return input_path

    def upload_books(self, files, names, on_card=None, end_session=True, metadata=None):
        host = self.device_host or PREFS['host']
        port = self.device_port or PREFS['port']
        upload_path = PREFS['path']
        chunk_size = PREFS['chunk_size']
        if chunk_size > 2048:
            self._log(f'[CrossPoint] chunk_size capped to 2048 (was {chunk_size})')
            chunk_size = 2048
        debug = PREFS['debug']

        # Validate input lengths
        if len(files) != len(names):
            raise ControlError(desc=f'Mismatch: {len(files)} files but {len(names)} names')

        # Normalize base upload path
        base_path = upload_path
        if not base_path.startswith('/'):
            base_path = '/' + base_path
        if base_path != '/' and base_path.endswith('/'):
            base_path = base_path[:-1]

        paths = []
        total = len(files)
        temp_files = []  # Track temp files for cleanup

        self._log(f'[CrossPoint] upload_books: {total} file(s) to {host}:{port}{base_path}')

        try:
            for i, (infile, name) in enumerate(zip(files, names)):
                self._log(f'[CrossPoint] [{i+1}/{total}] Processing: {name}')
                if hasattr(infile, 'read'):
                    filepath = getattr(infile, 'name', None)
                    if not filepath:
                        raise ControlError(desc='In-memory uploads are not supported')
                else:
                    filepath = infile

                # Convert EPUB if enabled
                converted_path = self._convert_epub(filepath)
                if converted_path != filepath:
                    temp_files.append(converted_path)
                    filepath = converted_path
                    self._log(f'[CrossPoint] [{i+1}/{total}] Using converted file')

                filename = os.path.basename(name)
                subdirs = []
                if metadata and i < len(metadata):
                    subdirs, filename = self._format_upload_path(metadata[i], filename)

                if subdirs:
                    target_dir = self._ensure_dir(base_path, subdirs)
                    self._log(f'[CrossPoint] [{i+1}/{total}] Target dir: {target_dir}')
                else:
                    target_dir = base_path

                if target_dir == '/':
                    lpath = '/' + filename
                else:
                    lpath = target_dir + '/' + filename

                # Bind loop variables via default arguments to avoid closure bug
                def _progress(sent, size, i=i, total=total):
                    if size > 0:
                        self.report_progress((i + sent / float(size)) / float(total),
                                             'Transferring books to device...')

                try:
                    ws_client.upload_file(
                        host,
                        port,
                        target_dir,
                        filename,
                        filepath,
                        chunk_size=chunk_size,
                        debug=debug,
                        progress_cb=_progress,
                        logger=self._log,
                    )
                    self._log(f'[CrossPoint] [{i+1}/{total}] Upload complete: {lpath}')
                except Exception as exc:
                    self._log(f'[CrossPoint] [{i+1}/{total}] Upload failed: {exc}')
                    raise

                paths.append((lpath, os.path.getsize(filepath)))

            self.report_progress(1.0, 'Transferring books to device...')
            self._log(f'[CrossPoint] All uploads complete: {len(paths)} file(s)')

        finally:
            # Clean up temp files
            for temp_path in temp_files:
                try:
                    os.remove(temp_path)
                except Exception as cleanup_err:
                    self._log(f'[CrossPoint] Failed to clean up temp file {temp_path}: {cleanup_err}')

        return paths

    def add_books_to_metadata(self, locations, metadata, booklists):
        self._log(f'[CrossPoint] add_books_to_metadata: {len(locations)} locations, '
                  f'{len(booklists)} booklists')
        metadata = iter(metadata)
        for location in locations:
            info = next(metadata)
            lpath = location[0]
            length = location[1]
            book = Book('', lpath, size=length, other=info)
            if booklists:
                booklists[0].add_book(book, replace_metadata=True)
                self._log(f'[CrossPoint] added to booklist: {lpath}')
            else:
                self._log(f'[CrossPoint] WARNING: booklists empty, could not add {lpath}')


    def _normalize_path(self, path):
        """Normalize path to use forward slashes and leading slash."""
        if not path:
            return ''
        p = path.replace('\\', '/')
        if not p.startswith('/'):
            p = '/' + p
        return p

    def delete_books(self, paths, end_session=True):
        """Delete books from device via WebDAV DELETE method."""
        host = self.device_host or PREFS['host']
        debug = PREFS['debug']

        # Normalize paths to use forward slashes (device expects Unix-style paths)
        normalized_paths = [self._normalize_path(p) for p in paths]

        self._log(f'[CrossPoint] delete_books: {len(normalized_paths)} file(s)')
        self._log(f'[CrossPoint] Host: {host}, Paths: {normalized_paths}')

        # Use WebDAV DELETE method (one file per request)
        from urllib.parse import quote

        deleted_paths = []
        failed_paths = []

        for path in normalized_paths:
            try:
                # URL encode the path
                encoded_path = quote(path)
                url = self._http_base() + encoded_path

                self._log(f'[CrossPoint] DELETE {url}')

                req = urllib.request.Request(url, method='DELETE')
                with urllib.request.urlopen(req, timeout=30) as resp:
                    if resp.status == 200 or resp.status == 204:
                        self._log(f'[CrossPoint] Deleted: {path}')
                        deleted_paths.append(path)
                    else:
                        self._log(f'[CrossPoint] WARNING: Delete failed for {path}: HTTP {resp.status}')
                        failed_paths.append(path)

            except urllib.error.HTTPError as exc:
                self._log(f'[CrossPoint] WARNING: Delete HTTP error for {path}: {exc.code}')
                failed_paths.append(path)
            except Exception as exc:
                self._log(f'[CrossPoint] WARNING: Delete failed for {path}: {exc}')
                failed_paths.append(path)

        if failed_paths:
            self._log(f'[CrossPoint] WARNING: {len(failed_paths)} file(s) failed to delete')
        else:
            self._log(f'[CrossPoint] All {len(deleted_paths)} file(s) deleted successfully')

        return deleted_paths

    def remove_books_from_metadata(self, paths, booklists):
        deleted = set(self._normalize_path(p) for p in paths)
        self._log(f'[CrossPoint] deleted paths: {sorted(deleted)}')

        removed = 0
        for bl in booklists:
            for book in tuple(bl):
                bpath = self._normalize_path(getattr(book, 'path', ''))
                blpath = self._normalize_path(getattr(book, 'lpath', ''))
                if bpath in deleted or blpath in deleted:
                    bl.remove_book(book)
                    removed += 1
        self._log(f'[CrossPoint] removed {removed} items from device list')

    def get_file(self, path, outfile, end_session=True, this_book=None, total_books=None):
        url = self._http_base() + '/download'
        params = urllib.parse.urlencode({'path': path})
        try:
            with urllib.request.urlopen(url + '?' + params, timeout=10) as resp:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    outfile.write(chunk)
        except Exception as exc:
            raise ControlError(desc=f'Failed to download {path}: {exc}')

    def _download_temp(self, path):
        from calibre.ptempfile import PersistentTemporaryFile
        tf = PersistentTemporaryFile(suffix='.epub')
        self.get_file(path, tf)
        tf.flush()
        tf.seek(0)
        return tf


    def eject(self):
        self.is_connected = False

    def is_dynamically_controllable(self):
        return 'crosspoint'

    def start_plugin(self):
        return None

    def stop_plugin(self):
        self.is_connected = False

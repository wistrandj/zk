import os
import re
import sys
import glob
import time
import socket
import logging
import sqlite3
import getpass
import argparse
import datetime as dt
from typing import *

# @Ideas:
# - If the new card is empty don't save it anywhere


log = logging.getLogger(__name__)

ALL_ZK_DIR = [
    '/tmp/x/zk',
    '/home/' + getpass.getuser() + '/timeline/zk',
    '/Users/' + getpass.getuser() + '/timeline/zk'
]
ZK_DIR = None
ZK_DB = None
ZK_RESTRICTIONS  = None
SCHEMA_PATH = '/usr/local/src/toybox/14/schema.sql'

RESTRICTIONS = None

class NotesDirectory:
    def __init__(self, directory: str):
        if not os.path.isdir(directory):
            raise EnvironmentError(f'Missing directory: {directory}')
        self._directory = directory

    def list_open_note_files(self) -> Set[str]:
        ''' Return full path to files in the directory. It can contain more files than
        in the database if the user created them. '''
        match = os.path.join(self._directory, '*')
        return set(glob.glob(match))


class NoteFiles:
    IS_MAJOR_NUMBER = re.compile('^[0-9]+$')
    IS_ANY_NOTE = re.compile('^[0-9]+|[0-9]+[a-z]|[0-9]+([a-z][0-9]+)+')

    def __init__(self, directory: NotesDirectory):
        self._directory = directory

    def fullpath_of_open_card(self, card_name: str) -> str:
        card_path = os.path.join(self._directory._directory, card_name)
        return card_path

    def find_major_notes(self) -> Set[str]:
        """ Return major note names in the directory (e.g. 123, 124). """
        notes = set()
        for file in self._directory.list_open_note_files():
            file = os.path.basename(file)
            if NoteFiles.IS_MAJOR_NUMBER.match(file):
                notes.add(file)
        return notes

    def find_all_notes(self) -> Set[str]:
        """ Return all note names in the directory (e.g. 123, 123a1) """
        notes = set()
        for file in self._directory.list_open_note_files():
            file = os.path.basename(file)
            if NoteFiles.IS_ANY_NOTE.match(file):
                notes.add(file)
        return notes

    def create_card_with_modified_time(self, card_name: str, content: str, modified_utc: int):
        """ Open an existing card from the database and set correct access and modified time """
        card_path = self.create_new_card(card_name, content)
        seconds_to_nanoseconds = 10**9
        time_utc_ns = time.time_ns() / seconds_to_nanoseconds
        access_utc_ns = int(time_utc_ns)
        modified_utc_ns = int(modified_utc * seconds_to_nanoseconds)
        os.utime(card_path, times=None, ns=(access_utc_ns, modified_utc_ns), follow_symlinks=True)

    def create_new_card(self, card_name: str, content: Union[str, bytes]):
        """ Create a new card """
        card_path = self.fullpath_of_open_card(card_name)
        if os.path.isfile(card_path):
            raise RuntimeError(f'Card exists: {card_path}')

        with open(card_path, 'wb') as fd:
            if isinstance(content, str):
                # Templates in the code are defined as strings
                fd.write(bytes(content, sys.getdefaultencoding()))
            else:
                fd.write(content)

        return card_path

    def modified_cards(self, persistent_notes: 'PersistentNotes') -> Set[str]:
        open_cards = self.find_all_notes()
        seconds_to_nanoseconds = 10**9
        modified_cards = set()
        for card_name in open_cards:
            card_path = self.fullpath_of_open_card(card_name)
            card_modified_at_ns = os.stat(card_path).st_mtime_ns
            persistent_card_modified_at_sec = persistent_notes.card_modified_utc_time_in_seconds(card_name)
            # @Xxx: 'zk show modified'
            persistent_card_modified_at_ns = persistent_card_modified_at_sec * seconds_to_nanoseconds

            if card_modified_at_ns > persistent_card_modified_at_ns:
                modified_cards.add(card_name)

        return modified_cards

    def new_cards(self, persistent_notes: 'PersistentNotes') -> Set[str]:
        open_cards = self.find_all_notes()
        persistent_cards = persistent_notes.find_all_notes()
        return open_cards.difference(persistent_cards)


class PersistentNotes:
    IS_MAJOR_NUMBER = re.compile('^[0-9]+$')
    IS_ANY_NOTE = re.compile('^[0-9]+|[0-9]+[a-z]|[0-9]+([a-z][0-9]+)+')

    def __init__(self, sqlite_connection):
        """ Start using fully initialized database """
        self._database_handle = sqlite_connection

    def commit(self):
        self._database_handle.commit()

    def find_major_notes(self) -> Set[str]:
        cursor = self._database_handle.cursor()
        cursor.execute('select name from notes')
        notes_in_database = cursor.fetchall()
        cursor.close()

        major_notes = set()
        for note in notes_in_database:
            note = note[0]
            if PersistentNotes.IS_MAJOR_NUMBER.match(note):
                major_notes.add(note)
        return major_notes

    def find_all_notes(self) -> Set[str]:
        cursor = self._database_handle.cursor()
        cursor.execute('select name from notes')
        notes_in_database = cursor.fetchall()
        cursor.close()

        major_notes = set()
        for note in notes_in_database:
            note = note[0]
            if PersistentNotes.IS_ANY_NOTE.match(note):
                major_notes.add(note)
        return major_notes


    def set_card_as_daily_card(self, card_name: str, date: dt.date):
        # @Question: Does the foreign key restriction raise an exception, if it doesn't exists?
        cursor = self._database_handle.cursor()
        args = (date.strftime('%F'), card_name)
        cursor.execute('insert into daily_notes(card_date, card_name) values (?, ?)', args)
        cursor.close()


    def daily_card_for_date(self, date: dt.date) -> Optional[str]:
        date_filter = (date.strftime('%F'),)
        cursor = self._database_handle.cursor()
        cursor.execute('select card_name from daily_notes where card_date = ?', date_filter)
        the_daily_card = cursor.fetchone()
        cursor.close()

        if the_daily_card:
            return the_daily_card[0]
        return None

    def save_card(self, card_name: str, card_path: str):
        notes = find_open_notes()
        if not os.path.isfile(card_path):
            raise EnvironmentError(f'Missing card: {card_path}')

        cursor = self._database_handle.cursor()
        stat = os.stat(card_path)
        created_utc  = int(stat.st_ctime)
        modified_utc = int(stat.st_mtime)
        with open(card_path, 'rb') as fd:
            content = fd.read()
            sql1 = ('insert into notes(name, content, created_utc, modified_utc) values (?, ?, ?, ?)')
            sql2 = ('on conflict(name) do update set content=excluded.content, modified_utc=excluded.modified_utc')
            args = (card_name, content, created_utc, modified_utc)

            cursor.execute(' '.join((sql1, sql2)), args)

        self.commit()

    def card_modified_utc_time_in_seconds(self, card_name: str) -> Optional[int]:
        cursor = self._database_handle.cursor()
        cursor.execute('select modified_utc from notes where name = ?', (card_name,))
        modified_time = cursor.fetchone()
        cursor.close()

        if not modified_time:
            return None
        return int(modified_time[0])


class Notes:
    def __init__(self, directory_path: str, database_path: str):
        self._sqlite_connection = sqlite3.connect(database_path)
        self._directory = NotesDirectory(directory_path)
        self._card_files = NoteFiles(self._directory)
        self._card_storage = PersistentNotes(self._sqlite_connection)

    @property
    def open_notes(self):
        return self._card_files

    @property
    def persistent_notes(self):
        return self._card_storage


def parse_restrictions(restrictions_file_content: str) -> List[Tuple[str, int, int]]:
    """ Read restrictions file
    :return: List of tuples (hostname, from, to)
    """
    restrictions = []
    for line in restrictions_file_content.splitlines():
        if line.startswith('#'):
            continue

        hostname, from_idx, to_idx = None, None, None

        for values in line.split():
            if '=' in values:
                key, value = values.split('=')
                if key == 'hostname':
                    hostname = value
                elif key == 'from':
                    from_idx = int(value)
                elif key == 'to':
                    to_idx = int(value)

        if hostname and from_idx and to_idx:
            # @Todo: Check that ranges are not overlapping
            restrictions.append((hostname, from_idx, to_idx))

    return restrictions


for directory in ALL_ZK_DIR:
    if os.path.isdir(directory):
        ZK_DIR = directory
        ZK_DB = os.path.dirname(ZK_DIR) + '/zk.db'
        ZK_RESTRICTIONS = os.path.dirname(ZK_DIR) + '/zk.restrictions'

        if os.path.isfile(ZK_RESTRICTIONS):
            RESTRICTIONS = parse_restrictions(ZK_RESTRICTIONS)

        break


def database_is_initialized():
    if not os.path.isfile(ZK_DB):
        return False

    with sqlite3.connect(ZK_DB) as db:
        cur = db.cursor()
        cur.execute('select 1')
        result = cur.fetchone()[0]

    return (result == 1)


def _smart_date(human_input):
    date = dt.date.today()
    words = ' '.join(human_input).lower().split()

    weekdays_short = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']
    weekdays_long  = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
    weekdays = weekdays_short + weekdays_long

    day = dt.timedelta(days=1)

    if len(words) == 0 or words[0] == 'today':
        return date
    elif words[0] == 'yesterday':
        return date - dt.timedelta(days=1)
    elif words[0] == 'tomorrow':
        return date + dt.timedelta(days=1)
    elif words[0] == 'next' and words[1] in weekdays:
        while range(7):
            date = date + dt.timedelta(days=1)
            short, long = date.strftime('%a %A').lower().split()
            if words[1] in [short, long]:
                return date
    elif words[0] == 'last':
        date = date - dt.timedelta(days=1)
        while range(7):
            date = date - dt.timedelta(days=1)
            short, long = date.strftime('%a %A').lower().split()
            if words[1] in [short, long]:
                return date

    raise ValueError('Invalid date string')


def create_and_initialize_database_file():
    if database_is_initialized():
        return

    with sqlite3.connect(ZK_DB) as db, open(SCHEMA_PATH, 'r') as schema:
        cursor = db.cursor()
        schema_sql = schema.read()
        cursor.executescript(schema_sql)


def populate_missing_note_entries_to_database():
    """ Add open notes in ZK_DIR and add them into database is missing """
    notes = find_open_notes()

    with sqlite3.connect(ZK_DB) as db:
        cursor = db.cursor()
        for note in notes:
            cursor.execute('select 1 from notes where name = ?', (note,))
            note_in_database = (cursor.fetchone() is not None)
            if note_in_database:
                continue

            print('Adding note', note, 'to the database')

            filepath = os.path.join(ZK_DIR, note)
            stat = os.stat(filepath)
            created_at  = int(stat.st_ctime)
            modified_at = int(stat.st_mtime)
            content = None
            with open(filepath, 'r') as fd:
                content = fd.read()
            sql = ('insert into notes(name, content, created_utc, modified_utc) values (?, ?, ?, ?)')
            args = (note, content, created_at, modified_at)

            cursor.execute(sql, args)


def save_open_notes_into_database(app: Notes):
    for card_name in app.open_notes.find_all_notes():
        card_path = app.open_notes.fullpath_of_open_card(card_name)
        app.persistent_notes.save_card(card_name, card_path)


def pack_open_notes_into_database(app: Notes):
    """ Save files into database and remove all files """
    save_open_notes_into_database(app)
    notes = find_open_notes()
    for note in notes:
        filepath = os.path.join(ZK_DIR, note)
        os.unlink(filepath)


def unpack_open_notes_from_database(app: Notes):
    with sqlite3.connect(ZK_DB) as db:
        cursor = db.cursor()
        cursor.execute('select name, content, created_utc, modified_utc from notes;')
        for row in cursor.fetchall():
            card_name, content, created_utc, modified_utc = row
            card_name, content, created_utc, modified_utc = str(card_name), bytes(content), int(created_utc), int(modified_utc)

            app.open_notes.create_card_with_modified_time(card_name=card_name, content=content, modified_utc=modified_utc)
            continue
            name = card_name
            filename = os.path.join(ZK_DIR, name)
            if not os.path.isfile(filename):
                with open(filename, 'wb') as fd:
                    fd.write(bytes(content))


def hostname():
    return socket.gethostname()



def find_open_notes():
    dir = NotesDirectory(ZK_DIR)
    open_notes = NoteFiles(dir)
    return open_notes.find_all_notes()


def create_card_and_open_editor(card_name: str, content: Optional[str]=None):
    """ Create a new card with optional contents.
    :param: card_name: name of the new card e.g. '19', '19a'
    :param content: Contents of the new file
    """
    filepath = os.path.join(ZK_DIR, card_name)

    if os.path.isfile(filepath) or os.path.isdir(filepath):
        raise EnvironmentError(f'Card {card_name} exists')

    if content is not None:
        with open(filepath, 'w') as fd:
            fd.write(content)

    os.system("vim -c 'normal! jj' " + filepath)


def next_available_major_note(open_files: NoteFiles, store: PersistentNotes) -> str:
    """ Return next available number that can be used for the next note. """
    files = open_files.find_major_notes()
    db_notes = store.find_major_notes()
    all_notes = files.union(db_notes)
    if len(all_notes) == 0:
        return '1'
    latest_note = max(set(int(major_note) for major_note in all_notes))
    return str(latest_note + 1)


def open_editor(card_path: str):
    os.system("vim -c 'normal! jj' " + card_path)


def get_branching_sub_level_card_name(major_or_sibling_card_name: str) -> Optional[str]:
    """ Open a second level card (i.e. 19c) but not a deeper level than that.
    That might need a special handling.
    :param major_or_sibling_card_name: Major or sub-level card name, e.g. '19', '19a'.
    :return: Name of the new card or None if sub cards reach to 'z'
    """
    major_card_re = re.compile(r'^([0-9]+)([a-z]?).*')
    match = major_card_re.match(major_or_sibling_card_name)
    if not match:
        raise RuntimeError('Invalid major card given for branching')
    major_card = match.group(1)

    db_cards = set()

    open_cards = find_open_notes()
    sibling_cards = set()

    for card in db_cards.union(open_cards):
        match = major_card_re.match(card)
        if major_card == match.group(1):
            if match.group(2) != '':
                sibling_cards.add(match.group(2))

    if len(sibling_cards) == 0:
        next_sibling = 'a'
    else:
        last_sibling = sorted(sibling_cards)[-1]
        if last_sibling == 'z':
            next_sibling = None
        else:
            next_sibling = chr(ord(last_sibling) + 1)

    if next_sibling is None:
        return None
    else:
        return f'{major_card}{next_sibling}'


def find_existing_daily_note(date: dt.date, *, app: Notes) -> Optional[str]:
    all_notes = app.open_notes.find_major_notes()
    expected_first_line = date.strftime('%F Daily')

    daily_note = None
    for note in all_notes:
        card_path = app.open_notes.fullpath_of_open_card(note)
        with open(card_path, 'r') as fd:
            content = fd.read(len(expected_first_line))

        if content == expected_first_line:
            found_daily_note = card_path
            break
    else:
        return None

    return os.path.basename(found_daily_note)


def create_new_open_card(content: str, app: Notes) -> str:
    card_name = next_available_major_note(app.open_notes, app.persistent_notes)
    card_path = app.open_notes.create_new_card(card_name=card_name, content=content)
    return card_path


def open_daily_card(date: dt.date, *, app: Notes) -> str:
    """ Open either existing daily note, or create a new card. """
    all_notes = app.open_notes.find_major_notes()
    expected_first_line = date.strftime('%F Daily')

    card_path = find_existing_daily_note(date, app=app)
    if not card_path:
        content = date.strftime('%F Daily\n\n\n')
        card_name = next_available_major_note(app.open_notes, app.persistent_notes)
        card_path = app.open_notes.create_new_card(card_name=card_name, content=content)

    return card_path


def initialize_database(database_path: str):
    create_and_initialize_database_file(database_path)
    # populate_missing_note_entries_to_database()


if __name__ == '__main__':
    subcommand = sys.argv[1]
    args = sys.argv[2:]
    print(f'Hi {ZK_DB} and {ZK_DIR}')

    # Initialize the database first
    main()

    app = notes = Notes(directory_path=ZK_DIR, database_path=ZK_DB)
    open_notes = app.open_notes
    persistent_notes = app.persistent_notes


    # if len(open_notes.find_major_notes()) == 0:
    #    raise EnvironmentError('This folder does not seem to be for notes. Initialize it first')

    # Actions
    if subcommand == 'card':
        content = dt.datetime.now().strftime('%F\n\n\n')
        card_path = create_new_open_card(content=content, app=notes)
        open_editor(card_path)
    elif subcommand == 'branch':
        card = get_branching_sub_level_card_name(args[0])
        if card:
            create_card_and_open_editor(card)
        else:
            raise RuntimeError("Too many notes for this major card. The sub-card 'z' already exists.")
    elif subcommand == 'daily':
        date = _smart_date(args)
        card_path = open_daily_card(date, app=notes)
        open_editor(card_path)
    elif subcommand == 'save':
        save_open_notes_into_database(app=notes)
    elif subcommand == 'pack':
        pack_open_notes_into_database(app=notes)
    elif subcommand == 'unpack':
        unpack_open_notes_from_database(app=notes)
    elif subcommand == 'show' and len(args) > 0:
        show_cards = set()
        if args[0] == 'modified':
            cards = app.open_notes.modified_cards(app.persistent_notes)
            print('Modified cards: ' + str(sorted(cards)))
        elif args[0] == 'new':
            cards = app.open_notes.new_cards(app.persistent_notes)
            print('New cards: ' + str(sorted(cards)))

    elif subcommand == 'init':
        pass


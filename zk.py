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

import note_folder as NF
from note_folder import NoteFiles
from note_folder import NotesDirectory
from note_database import NoteDatabase
import daily

log = logging.getLogger(__name__)
ZK_DIR = None
ZK_DB = None


class Notes:
    def __init__(self, directory_path: str, database_path: str):
        self._sqlite_connection = sqlite3.connect(database_path)
        self._directory = NotesDirectory(directory_path)
        self._card_files = NoteFiles(self._directory)
        self._card_storage = NoteDatabase(self._sqlite_connection)

    @property
    def open_notes(self):
        return self._card_files

    @property
    def persistent_notes(self):
        return self._card_storage

    @property
    def database_handle(self):
        return self._sqlite_connection


def check_database(database_path: str) -> bool:
    """ Check if there's an notes database in the path of giben argument
    @Robustness: Doesn't check if the database is readable and all tables
    """
    return os.path.isfile(database_path)


def check_open_notes_directory(database_handle: sqlite3.Connection) -> str:
    """ Return the directory to open notes. It can be either saved in the database, or current working directory.
    @Robustness: Not exception safe and doesn't check if the directory is writable
    """
    cursor = database_handle.cursor()
    cursor.execute('select absolute_path from default_directory;')
    notes_folder_row = cursor.fetchone()
    cursor.close()

    if notes_folder_row and os.path.isdir(notes_folder_row[0]):
        note_folder = notes_folder_row[0]
        if not os.path.isdir(note_folder):
            raise EnvironmentError(f'The notes folder {note_folder} does not exists!')
        return note_folder

    return os.getcwd()


def save_open_notes_into_database(app: Notes):
    for card_name in app.open_notes.find_all_notes():
        card_path = app.open_notes.fullpath_of_open_card(card_name)
        app.persistent_notes.save_card(card_name, card_path)


def remove_default_location(app: Notes):
    with app.database_handle as db:
        cursor = db.cursor()
        cursor.execute('delete from default_directory')
        db.commit()


def set_default_location(app: Notes, note_folder: str):
    if not os.path.isdir(note_folder):
        raise EnvironmentError('The folder is missing')

    with app.database_handle:
        args = (os.path.abspath(note_folder),)
        cursor = app.database_handle.cursor()
        cursor.execute('delete from default_directory')
        cursor.execute('insert into default_directory(absolute_path) values (?)', args)


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


def next_available_major_note(open_files: NoteFiles, store: NoteDatabase) -> str:
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


def create_new_open_card(content: str, app: Notes) -> str:
    card_name = next_available_major_note(app.open_notes, app.persistent_notes)
    card_path = app.open_notes.create_new_card(card_name=card_name, content=content)
    return card_path


if __name__ == '__main__':
    assert sys.argv[1] == '--database'
    database_path = sys.argv[2]
    assert str(database_path)
    subcommand = sys.argv[3]
    args = sys.argv[4:]

    # @Note: Database initialization, execute with subcommands 'init' or 'init-sql <number>'
    sql_script = None
    if subcommand == 'init':
        developing_directory = os.path.dirname(sys.argv[0])
        sql_directory = os.path.join(developing_directory, 'sql')
        sql_script = os.path.join(sql_directory, 'schema.sql')
    elif subcommand == 'init-sql':
        # Temporary command for developing. Later: merge sql files into single file
        developing_directory = os.path.dirname(sys.argv[0])
        sql_directory = os.path.join(developing_directory, 'sql')
        sql_number = int(args[0])
        if sql_number > 0:
            sql_script = os.path.join(sql_directory, f'schema.{sql_number}.sql')
    if sql_script:
        if not os.path.isfile(sql_script):
            raise EnvironmentError('Invalid developing sql script!')
        with sqlite3.connect(database_path) as database_handle:
            with open(sql_script, 'r') as schema:
                cursor = database_handle.cursor()
                schema_sql = schema.read()
                cursor.executescript(schema_sql)
        sys.exit(0)  # The only command was to initialize the database

    if database_path and not check_database(database_path):
        raise EnvironmentError('the database is missing')

    if not database_path:
        # Use In-memory database if the user didn't want to use anything else.
        # This allows to use zk for open notes without a database.
        database_path = ':memory:'
        raise RuntimeError('Not supported yet')

    with sqlite3.connect(database_path) as connection_handle:
        note_folder = check_open_notes_directory(connection_handle)

    # @Todo: remove all references to ZK_DB and ZK_DIR
    ZK_DB, ZK_DIR = database_path, note_folder

    app = notes = Notes(directory_path=note_folder, database_path=database_path)
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
        # Saves the card immediately into the database
        date = daily.smart_date(args)
        card_name = daily.daily_card_name(date, notes.database_handle)
        if not card_name:
            content = date.strftime('%F Daily\n\n\n')
            card_path = create_new_open_card(content=content, app=notes)
            card_name = os.path.basename(card_path)
            notes.persistent_notes.save(card_name, card_path)
            daily.set_the_daily_card(card_name, date, notes.database_handle)
        else:
            card_path = notes.open_notes.fullpath_of_open_card(card_name)
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
            cards = NF.modified_cards(notes.open_notes, notes.database_handle)
            print('Modified cards: ' + str(sorted(cards)))
        elif args[0] == 'new':
            cards = NF.new_cards(notes.open_notes, notes.database_handle)
            print('New cards: ' + str(sorted(cards)))
    elif subcommand == '--set-default-directory':
        set_default_location(notes, args[0])
    elif subcommand == '--remove-default-directory':
        remove_default_location(notes)
    else:
        log.info('No command given')
        print('No command given')


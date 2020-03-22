import os
import re
import sys
import glob
import time
import sqlite3
from typing import *


SECONDS_TO_NANOSECONDS = 10**9

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


def modified_cards(note_files: NoteFiles, database_handle: sqlite3.Connection):
    """ @Robustness: Exception safety """
    open_cards = note_files.find_all_notes()

    cursor = database_handle.cursor()
    cursor.execute('select name, modified_utc from notes')
    list_of_names_and_mtimes = cursor.fetchall()
    cursor.close()

    modified = set()
    for card_name, mtime in list_of_names_and_mtimes:
        mtime = int(mtime)
        if card_name in open_cards:
            card_path = note_files.fullpath_of_open_card(card_name)
            card_mtime_ns = os.stat(card_path).st_mtime_ns  # card_modified_utc_time_in_seconds(...)
            note_mtime_ns = mtime * SECONDS_TO_NANOSECONDS

            if card_mtime_ns > note_mtime_ns:
                modified.add(card_name)

    return modified


def new_cards(note_files: NoteFiles, database_handle: sqlite3.Connection):
    """ @Robustness: Exception safety """
    open_cards = note_files.find_all_notes()

    cursor = database_handle.cursor()
    cursor.execute('select name from notes')
    list_of_notes = cursor.fetchall()
    cursor.close()

    notes = set(note[0] for note in list_of_notes)
    return open_cards.difference(notes)


import re
import sqlite3
from typing import *

from note_folder import NoteFiles
from note_database import NoteDatabase


def next_available_major_note(open_files: NoteFiles, store: NoteDatabase) -> str:
    """ Return next available number that can be used for the next note. """
    files = open_files.find_major_notes()
    db_notes = store.find_major_notes()
    all_notes = files.union(db_notes)
    if len(all_notes) == 0:
        return '1'
    latest_note = max(set(int(major_note) for major_note in all_notes))
    return str(latest_note + 1)


def next_available_subcard_name(major_or_sibling_card_name: str, folder: NoteFiles, database: NoteDatabase) -> Optional[str]:
    """ Open a second level card (i.e. 19c) but not any deeper level than that.
    That might need a special handling.
    :param major_or_sibling_card_name: Major or sub-level card name, e.g. '19', '19a'.
    :return: Name of the new card or None if sub cards reach to 'z'
    """
    major_card_re = re.compile(r'^([0-9]+)([a-z]?).*')
    match = major_card_re.match(major_or_sibling_card_name)
    if not match:
        raise RuntimeError('Invalid major card given for branching')
    major_card = match.group(1)

    open_cards = folder.find_all_notes()
    db_cards = database.find_all_notes()

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



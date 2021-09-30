#! /usr/bin/env python
import csv
import os
import pprint

import git
import yaml

from review_template import entry_hash_function
from review_template import importer
from review_template import utils

with open('shared_config.yaml') as shared_config_yaml:
    shared_config = yaml.load(shared_config_yaml, Loader=yaml.FullLoader)
HASH_ID_FUNCTION = shared_config['params']['HASH_ID_FUNCTION']
with open('private_config.yaml') as private_config_yaml:
    private_config = yaml.load(private_config_yaml, Loader=yaml.FullLoader)

MAIN_REFERENCES = \
    entry_hash_function.paths[HASH_ID_FUNCTION]['MAIN_REFERENCES']

DEBUG_MODE = (1 == private_config['params']['DEBUG_MODE'])

entry_type_mapping = {'a': 'article', 'i': 'inproceedings', 'b': 'book'}


def create_commit(bib_database):

    r = git.Repo('')
    utils.save_bib_file(bib_database, MAIN_REFERENCES)

    if MAIN_REFERENCES in [item.a_path for item in r.index.diff(None)] or \
            MAIN_REFERENCES in r.untracked_files:

        r.index.add([MAIN_REFERENCES])

        hook_skipping = 'false'
        if not DEBUG_MODE:
            hook_skipping = 'true'
        r.index.commit(
            'Complete records for import',
            author=git.Actor(
                'manual (using complete_manual.py)', ''),
            skip_hooks=hook_skipping
        )

    return


def apply_completion_edits(bib_database):

    completion_edits = []
    if os.path.exists('search/completion_edits.csv'):
        with open('search/completion_edits.csv') as read_obj:
            csv_reader = csv.DictReader(read_obj)
            line_count = 0
            for row in csv_reader:
                if line_count == 0:
                    line_count += 1
                completion_edits.append([row['source_file_path'],
                                         row['source_id'],
                                         row['key'],
                                         row['value']])

    for entry in bib_database.entries:
        for completion_edit in completion_edits:
            if completion_edit[0] == entry.get('source_file_path', 'NA') and \
                    completion_edit[1] == entry.get('source_id', 'NA'):
                entry[completion_edit[2]] = completion_edit[3]

    return bib_database


def main():

    print('Loading records for manual completion...')

    bib_database = utils.load_references_bib(
        modification_check=True, initialize=False,
    )

    citation_key_list = [entry['ID'] for entry in bib_database.entries]

    pp = pprint.PrettyPrinter(indent=4, width=140)
    for entry in [x for x in bib_database.entries
                  if 'needs_manual_completion' == x['status']]:

        # Escape sequence to clear terminal output for each new comparison
        print(chr(27) + '[2J')
        pp.pprint(entry)
        if 'title' in entry:
            print('https://scholar.google.de/scholar?hl=de&as_sdt=0%2C5&q=' +
                  entry['title'].replace(' ', '+'))
        if 'n' == input('ENTRYTYPE=' + entry['ENTRYTYPE'] + ' correct?'):
            correct_entry_type = input('Correct type: ' +
                                       'a (article), i (inproceedings), ' +
                                       'b (book), o (other)')
            assert correct_entry_type in ['a', 'i', 'b', 'o']
            correct_entry_type = [value for (key, value)
                                  in entry_type_mapping.items()
                                  if key == correct_entry_type]
            entry['ENTRYTYPE'] = correct_entry_type[0]

        if 'article' == entry['ENTRYTYPE']:
            for field in ['title', 'author', 'year', 'journal', 'volume']:
                if field not in entry:
                    value = input('Please provide the ' + field + ' (or NA)')
                    entry[field] = value
            if 'issue' not in entry and 'number' not in entry:
                value = input('Please provide the number (or NA)')
                entry['number'] = value

        if 'inproceedings' == entry['ENTRYTYPE']:
            for field in ['title', 'author', 'booktitle', 'year']:
                if field not in entry:
                    value = input('Please provide the ' + field + ' (or NA)')
                    entry[field] = value

        if 'book' == entry['ENTRYTYPE']:
            for field in ['title', 'author', 'year']:
                if field not in entry:
                    value = input('Please provide the ' + field + ' (or NA)')
                    entry[field] = value

        # ELSE: title, author, year, any-container-title

        if importer.is_sufficiently_complete(entry):
            # Note: NA is used to indicate that there is no value for the field
            # (but it is not needed), e.g., some journals have no issue numbers
            for key in list(entry):
                if 'NA' == entry[key]:
                    del entry[key]

            entry = importer.drop_fields(entry)
            hid = entry_hash_function.create_hash[HASH_ID_FUNCTION](entry)
            entry.update(hash_id=hid)
            entry.update(ID=utils.generate_citation_key_blacklist(
                entry, citation_key_list,
                entry_in_bib_db=True,
                raise_error=False))
            entry.update(status='imported')
            citation_key_list.append(entry['ID'])

            utils.save_bib_file(bib_database, MAIN_REFERENCES)

    create_commit(bib_database)


if __name__ == '__main__':
    main()

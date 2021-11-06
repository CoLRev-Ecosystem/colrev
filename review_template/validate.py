#! /usr/bin/env python
import itertools
import logging
import multiprocessing as mp
import os
import pprint
from itertools import chain

import bibtexparser
import dictdiffer
import git
import pipeline_validation_hooks
from bashplotlib.histogram import plot_hist
from bibtexparser.customization import convert_to_unicode
from pipeline_validation_hooks import check  # noqa: F401

from review_template import dedupe
from review_template import repo_setup
from review_template import status
from review_template import utils


def load_records(bib_file):

    with open(bib_file) as bibtex_file:
        individual_bib_db = bibtexparser.bparser.BibTexParser(
            customization=convert_to_unicode, common_strings=True,
        ).parse_file(bibtex_file, partial=True)
        search_file = os.path.basename(bib_file)
        for record in individual_bib_db.entries:
            record['origin'] = search_file + '/' + record['ID']

    return individual_bib_db.entries


def get_search_records():

    pool = mp.Pool(repo_setup.config['CPUS'])
    records = pool.map(load_records, utils.get_bib_files())
    records = list(chain(*records))

    return records


def validate_preparation_changes(bib_db, search_records):

    print('Calculating preparation differences...')
    change_diff = []
    for record in bib_db.entries:
        if 'changed_in_target_commit' not in record:
            continue
        del record['changed_in_target_commit']
        del record['rev_status']
        del record['md_status']
        del record['pdf_status']
        # del record['origin']
        for cur_record_link in record['origin'].split(';'):
            prior_records = [x for x in search_records
                             if cur_record_link in x['origin'].split(',')]
            for prior_record in prior_records:
                similarity = dedupe.get_record_similarity(record, prior_record)
                change_diff.append([record['ID'], cur_record_link, similarity])

    change_diff = [[e1, e2, 1-sim] for [e1, e2, sim] in change_diff if sim < 1]
    # sort according to similarity
    change_diff.sort(key=lambda x: x[2], reverse=True)

    if 0 == len(change_diff):
        print('No substantial differences found.')

    plot_hist([sim for [e1, e2, sim] in change_diff],
              bincount=100, xlab=True, showSummary=True)
    input('continue')

    pp = pprint.PrettyPrinter(indent=4)
    for eid, record_link, difference in change_diff:
        # Escape sequence to clear terminal output for each new comparison
        os.system('cls' if os.name == 'nt' else 'clear')
        print('Record with ID: ' + eid)

        print('Difference: ' + str(round(difference, 4)) + '\n\n')
        record_1 = [x for x in search_records if record_link == x['origin']]
        pp.pprint(record_1[0])
        record_2 = [x for x in bib_db.entries if eid == x['ID']]
        pp.pprint(record_2[0])

        print('\n\n')
        for diff in list(dictdiffer.diff(record_1, record_2)):
            # Note: may treat fields differently (e.g., status, ID, ...)
            pp.pprint(diff)

        if 'n' == input('continue (y/n)?'):
            break
        # input('TODO: correct? if not, replace current record with old one')

    return


def validate_merging_changes(bib_db, search_records):

    os.system('cls' if os.name == 'nt' else 'clear')
    print('Calculating differences between merged records...')
    change_diff = []
    merged_records = False
    for record in bib_db.entries:
        if 'changed_in_target_commit' not in record:
            continue
        del record['changed_in_target_commit']
        if ';' in record['origin']:
            merged_records = True
            els = record['origin'].split(';')
            duplicate_el_pairs = list(itertools.combinations(els, 2))
            for el_1, el_2 in duplicate_el_pairs:
                record_1 = [x for x in search_records if el_1 == x['origin']]
                record_2 = [x for x in search_records if el_2 == x['origin']]

                similarity = \
                    dedupe.get_record_similarity(record_1[0], record_2[0])
                change_diff.append([el_1, el_2, similarity])

    change_diff = [[e1, e2, 1-sim] for [e1, e2, sim] in change_diff if sim < 1]

    # sort according to similarity
    change_diff.sort(key=lambda x: x[2], reverse=True)

    if 0 == len(change_diff):
        if merged_records:
            print('No substantial differences found.')
        else:
            print('No merged records')

    pp = pprint.PrettyPrinter(indent=4)

    for el_1, el_2, difference in change_diff:
        # Escape sequence to clear terminal output for each new comparison
        os.system('cls' if os.name == 'nt' else 'clear')

        print('Differences between merged records:' +
              f' {round(difference, 4)}\n\n')
        record_1 = [x for x in search_records if el_1 == x['origin']]
        pp.pprint(record_1[0])
        record_2 = [x for x in search_records if el_2 == x['origin']]
        pp.pprint(record_2[0])

        if 'n' == input('continue (y/n)?'):
            break
        # TODO: explain users how to change it/offer option to reverse!

    return


def load_bib_db(target_commit):

    if 'none' == target_commit:
        print('Loading data...')
        bib_db = utils.load_main_refs(mod_check=False)
        [x.update(changed_in_target_commit='True') for x in bib_db.entries]

    else:
        print('Loading data from history...')
        repo = git.Repo()

        MAIN_REFERENCES = repo_setup.paths['MAIN_REFERENCES']

        revlist = (
            (commit.hexsha, (commit.tree / MAIN_REFERENCES).data_stream.read())
            for commit in repo.iter_commits(paths=MAIN_REFERENCES)
        )
        found = False
        for commit, filecontents in list(revlist):
            if found:  # load the MAIN_REFERENCES in the following commit
                prior_bib_db = bibtexparser.loads(filecontents)
                break
            if commit == target_commit:
                bib_db = bibtexparser.loads(filecontents)
                found = True

        # determine which records have been changed (prepared or merged)
        # in the target_commit
        for record in bib_db.entries:
            prior_record = [x for x in prior_bib_db.entries
                            if x['ID'] == record['ID']][0]
            # Note: the following is an exact comparison of all fields
            if record != prior_record:
                record.update(changed_in_target_commit='True')

    return bib_db


def validate_properties(target_commit):
    # TODO: option: --history: check all preceding commits (create a list...)
    repo = git.Repo()
    cur_sha = repo.head.commit.hexsha
    cur_branch = repo.active_branch.name
    logging.info(f'Current commit: {cur_sha} (branch {cur_branch})')

    if not target_commit:
        target_commit = cur_sha
    if repo.is_dirty() and not target_commit == cur_sha:
        print('Error: Need a clean repository to validate properties '
              'of prior commit')
        return
    if not target_commit == cur_sha:
        print(f'Check out target_commit = {target_commit}')
        repo.git.checkout(target_commit)

    completeness_condition = status.get_completeness_condition()
    if completeness_condition:
        print('Completeness of iteration'.ljust(32, ' ') + 'YES (validated)')
    else:
        print('Completeness of iteration'.ljust(32, ' ') + 'NO')
    if 0 == pipeline_validation_hooks.check.main():
        print('Traceability of records'.ljust(32, ' ') + 'YES (validated)')
        print('Consistency (based on hooks)' .ljust(32, ' ') +
              'YES (validated)')
    else:
        print('Traceability of records'.ljust(32, ' ') + 'NO')
        print('Consistency (based on hooks)' .ljust(32, ' ') + 'NO')

    repo.git.checkout(cur_branch, force=True)

    return


def main(scope, properties=False, target_commit=None):

    if properties:
        validate_properties(target_commit)
        return

    #
    # TODO: extension: filter for changes of contributor (git author)

    bib_db = load_bib_db(target_commit)

    # Note: search records are considered immutable
    # we therefore load the latest files
    search_records = get_search_records()

    if 'prepare' == scope or 'all' == scope:
        validate_preparation_changes(bib_db, search_records)

    if 'merge' == scope or 'all' == scope:
        validate_merging_changes(bib_db, search_records)

    return


if __name__ == '__main__':
    main()

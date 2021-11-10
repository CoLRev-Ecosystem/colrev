#! /usr/bin/env python
import itertools
import logging
import multiprocessing as mp
import os
import pprint
import re
import shutil
from datetime import datetime
from itertools import chain

import bibtexparser
import pandas as pd
import requests
from bibtexparser.bibdatabase import BibDatabase
from bibtexparser.bparser import BibTexParser
from bibtexparser.customization import convert_to_unicode

import docker
from review_template import grobid_client
from review_template import repo_setup
from review_template import utils

logging.getLogger('bibtexparser').setLevel(logging.CRITICAL)

SEARCH_DETAILS = repo_setup.paths['SEARCH_DETAILS']
MAIN_REFERENCES = repo_setup.paths['MAIN_REFERENCES']
BATCH_SIZE = repo_setup.config['BATCH_SIZE']
pp = pprint.PrettyPrinter(indent=4, width=140)

search_type_opts = ['DB', 'TOC', 'BACK_CIT', 'FORW_CIT', 'OTHER']


def get_search_files():
    supported_extensions = ['ris', 'bib', 'end',
                            'txt', 'csv', 'txt',
                            'xlsx', 'pdf']
    files = []
    search_dir = os.path.join(os.getcwd(), 'search/')
    files = [os.path.join(search_dir, x)
             for x in os.listdir(search_dir)
             if any(x.endswith(ext) for ext in supported_extensions)]
    return files


def get_imported_record_links():

    imported_record_links = []
    try:
        imported_record_links = pd.read_csv('imported_record_links.csv',
                                            header=None)
        imported_record_links = \
            imported_record_links[imported_record_links.columns[0]].tolist()
    except pd.errors.EmptyDataError:
        # ok if no search results have been imported before
        if not os.path.exists(MAIN_REFERENCES):
            pass

    return imported_record_links


def load_records(filepath):

    imported_record_links = get_imported_record_links()

    search_db = load_search_results_file(filepath)

    if search_db is None:
        return []

    search_file = os.path.basename(filepath)
    record_list = []
    for record in search_db.entries:
        record['origin'] = search_file + '/' + record['ID']
        if record['origin'] in imported_record_links:
            logging.debug(f'skipped record {record["ID"]} (already imported)')
            continue

        record.update(rev_status='retrieved')
        record.update(md_status='retrieved')
        logging.debug(
            f'append record {record["ID"]} \n{pp.pformat(record)}\n\n')
        record_list.append(record)

    return record_list


def save_imported_record_links(bib_db):
    imported_record_links = [x['origin'].split(';')
                             for x in bib_db.entries
                             if 'origin' in x]
    imported_record_links = list(itertools.chain(*imported_record_links))

    with open('imported_record_links.csv', 'a') as fd:
        for el in imported_record_links:
            fd.write(el + '\n')

    return


def import_record(record):
    logging.debug(f'import_record {record["ID"]}: \n{pp.pformat(record)}\n\n')

    if 'retrieved' != record['md_status']:
        return record

    # For better readability of the git diff:
    fields_to_process = [
        'author', 'year', 'title',
        'journal', 'booktitle', 'series',
        'volume', 'number', 'pages', 'doi',
        'abstract'
    ]
    for field in fields_to_process:
        if field in record:
            record[field] = record[field].replace('\n', ' ')\
                .rstrip().lstrip()\
                .replace('{', '').replace('}', '')

    record.update(md_status='imported')

    return record


def source_heuristics(search_file):
    with open(search_file) as f:
        for line in f.readlines():
            if 'bibsource = {dblp computer science' + \
                    ' bibliography, https://dblp.org}' in line:
                return 'DBLP'

    return None


def check_update_search_details(search_files):

    search_details = utils.load_search_details()

    for search_file_path in search_files:
        search_file = os.path.basename(search_file_path)
        if search_file not in [x['filename'] for x in search_details]:
            source_name = source_heuristics(search_file_path)
            print(f'Please provide details for {search_file}')
            search_type = 'TODO'
            while search_type not in search_type_opts:
                print(f'Search type options: {search_type_opts}')
                search_type = input('Enter search type'.ljust(40, ' ') + ': ')
            if source_name is None:
                source_name = input('Enter source name (e.g., GoogleScholar)'
                                    .ljust(40, ' ') + ': ')
            else:
                print('Source name'.ljust(40, ' ') + f': {source_name}')
            source_url = input('Enter source_url'.ljust(40, ' ') + ': ')
            search_parameters = input('Enter search_parameters'
                                      .ljust(40, ' ') + ': ')
            comment = input('Enter a comment (or NA)'.ljust(40, ' ') + ': ')
            new_record = {'filename': search_file,
                          'search_type': search_type,
                          'source_name': source_name,
                          'source_url': source_url,
                          'search_parameters': search_parameters,
                          'comment': comment,
                          }
            search_details.append(new_record)
            logging.info(f'Added infos to {SEARCH_DETAILS}:'
                         f' \n{pp.pformat(new_record)}')

    utils.save_search_details(search_details)

    return


def rename_search_files(search_files):
    ret_list = []
    date_regex = r'^\d{4}-\d{2}-\d{2}'
    for search_file in search_files:
        if re.search(date_regex, os.path.basename(search_file)):
            ret_list.append(search_file)
        else:
            new_filename = \
                os.path.join(os.path.dirname(search_file),
                             datetime.today().strftime('%Y-%m-%d-') +
                             os.path.basename(search_file))
            new_filename = new_filename.replace(' ', '_')
            os.rename(search_file, new_filename)
            ret_list.append(new_filename)
    return ret_list


def load_all_records():

    bib_db = utils.load_main_refs(mod_check=True, init=True)
    save_imported_record_links(bib_db)
    load_pool = mp.Pool(repo_setup.config['CPUS'])
    search_files = get_search_files()
    search_files = rename_search_files(search_files)
    if any('.pdf' in x for x in search_files):
        grobid_client.start_grobid()
    check_update_search_details(search_files)
    additional_records = load_pool.map(load_records, search_files)
    load_pool.close()
    load_pool.join()
    additional_records = list(chain(bib_db.entries, *additional_records))

    if os.path.exists('imported_record_links.csv'):
        os.remove('imported_record_links.csv')

    return additional_records


def bibutils_convert(script, data):

    assert script in ['ris2xml', 'end2xml',
                      'endx2xml', 'isi2xml',
                      'med2xml', 'xml2bib']

    if 'xml2bib' == script:
        script = script + ' -b -w '

    if isinstance(data, str):
        data = data.encode()

    client = docker.APIClient()
    try:
        cur_tag = docker.from_env().images.get('bibutils').tags[0]
        logging.info(f'Running docker container created from {cur_tag}')
        container = \
            client.create_container('bibutils', script, stdin_open=True)
    except docker.errors.ImageNotFound:
        logging.info('Docker image not found')
        return ''
        pass

    sock = client.attach_socket(container,
                                params={'stdin': 1, 'stdout': 1,
                                        'stderr': 1, 'stream': 1})
    client.start(container)

    sock._sock.send(data)
    sock._sock.close()
    sock.close()

    client.wait(container)
    # status = client.wait(container)
    # status_code = status['StatusCode']
    stdout = client.logs(container, stderr=False).decode()
    # stderr = client.logs(container, stdout=False).decode()

    client.remove_container(container)

    # print('Exit: {}'.format(status_code))
    # print('log stdout: {}'.format(stdout))
    # print('log stderr: {}'.format(stderr))

    # TODO: else: raise error!

    return stdout


def getbib(file):
    with open(file) as bibtex_file:
        contents = bibtex_file.read()
        bib_r = re.compile(r'^@.*{.*,', re.M)
        if len(re.findall(bib_r, contents)) == 0:
            logging.error(f'Not a bib file? {os.path.basename(file)}')
            db = None
        if 'Early Access Date' in contents:
            logging.error('Replace Early Access Date in bibfile before '
                          f'loading! {os.path.basename(file)}')
            return None

        else:
            with open(file) as bibtex_file:
                db = BibTexParser(
                    customization=convert_to_unicode,
                    ignore_nonstandard_types=False,
                    common_strings=True,
                ).parse_file(bibtex_file, partial=True)
    return db


def ris2bib(file):
    with open(file) as reader:
        data = reader.read(4096)
    if 'TY  - ' not in data:
        logging.error('Error: Not a ris file? ' + os.path.basename(file))
        return None

    with open(file) as reader:
        data = reader.read()

    data = bibutils_convert('ris2xml', data)
    data = bibutils_convert('xml2bib', data)
    db = bibtexparser.loads(data)
    return db


def end2bib(file):
    with open(file) as reader:
        data = reader.read(4096)
    if '%%T ' not in data:
        logging.error('Error: Not an end file? ' + os.path.basename(file))
        return None

    with open(file) as reader:
        data = reader.read()

    data = bibutils_convert('end2xml', data)
    data = bibutils_convert('xml2bib', data)
    db = bibtexparser.loads(data)
    return db


def txt2bib(file):
    grobid_client.check_grobid_availability()
    with open(file) as f:
        references = [line.rstrip() for line in f]

    # Note: processCitationList currently not working!??!
    data = ''
    ind = 0
    for ref in references:
        options = {}
        options['consolidateCitations'] = '1'
        options['citations'] = ref
        r = requests.post(
            grobid_client.get_grobid_url() + '/api/processCitation',
            data=options,
            headers={'Accept': 'application/x-bibtex'}
        )
        ind += 1
        data = data + '\n' + r.text.replace('{-1,', '{' + str(ind) + ',')

    db = bibtexparser.loads(data)
    return db


def preprocess_records(data):
    for x in data:
        # TODO: more sophisticated setting of ENTRYTYPE, ID is needed.
        # could also use simple numbers as IDs...
        x['ENTRYTYPE'] = 'article'
        if 'citation_key' in x.keys():
            x['ID'] = x.pop('citation_key')
        for k, v in x.items():
            x[k] = str(v)

    return data


def csv2bib(file):
    try:
        data = pd.read_csv(file)
    except pd.errors.ParserError:
        logging.error('Error: Not a csv file? ' + os.path.basename(file))
        pass
        return None
    data.columns = data.columns.str.replace(' ', '_')
    data.columns = data.columns.str.replace('-', '_')
    data = data.to_dict('records')
    data = preprocess_records(data)

    db = BibDatabase()
    db.entries = data
    return db


def xlsx2bib(file):
    try:
        data = pd.read_excel(file)
    except pd.errors.ParserError:
        logging.error('Error: Not an xlsx file: ' + os.path.basename(file))
        pass
        return None
    data.columns = data.columns.str.replace(' ', '_')
    data.columns = data.columns.str.replace('-', '_')
    data = data.to_dict('records')
    data = preprocess_records(data)

    db = BibDatabase()
    db.entries = data
    return db


def move_to_pdf_dir(filepath):
    PDF_DIRECTORY = repo_setup.paths['PDF_DIRECTORY']
    # We should avoid re-extracting data from PDFs repeatedly (e.g., status.py)
    if not os.path.exists(PDF_DIRECTORY):
        os.mkdir(PDF_DIRECTORY)
        shutil.move(filepath, os.path.join(PDF_DIRECTORY, filepath))
    return


# curl -v --form input=@./profit.pdf localhost:8070/api/processHeaderDocument
# curl -v --form input=@./thefile.pdf -H "Accept: application/x-bibtex"
# -d "consolidateHeader=0" localhost:8070/api/processHeaderDocument
def pdf2bib(file):
    grobid_client.check_grobid_availability()

    # https://github.com/kermitt2/grobid/issues/837
    r = requests.post(
        grobid_client.get_grobid_url() + '/api/processHeaderDocument',
        headers={'Accept': 'application/x-bibtex'},
        params={'consolidateHeader': '1'},
        files=dict(input=open(file, 'rb'))
    )

    if 200 == r.status_code:
        db = bibtexparser.loads(r.text)
        with open(file.replace('.pdf', '.bib'), 'w') as f:
            f.write(r.text)
        move_to_pdf_dir(file)
        return db
    if 500 == r.status_code:
        logging.error(f'Not a readable pdf file: {os.path.basename(file)}')
        print(f'Grobid: {r.text}')
        return None

    print(f'Status: {r.status_code}')
    print(f'Response: {r.text}')
    return None


def pdfRefs2bib(file):
    grobid_client.check_grobid_availability()

    r = requests.post(
        grobid_client.get_grobid_url() + '/api/processReferences',
        files=dict(input=open(file, 'rb')),
        data={'consolidateHeader': '0', 'consolidateCitations': '1'},
        headers={'Accept': 'application/x-bibtex'}
    )
    if 200 == r.status_code:
        db = bibtexparser.loads(r.text)
        move_to_pdf_dir(file.replace('.pdf', '.bib'))
        return db
    if 500 == r.status_code:
        logging.error(f'Not a readable pdf file? {os.path.basename(file)}')
        print(f'Grobid: {r.text}')
        return None

    print(f'Status: {r.status_code}')
    print(f'Response: {r.text}')
    return None


def load_search_results_file(search_file_path):

    search_file = os.path.basename(search_file_path)

    importer_scripts = {'bib': getbib,
                        'ris': ris2bib,
                        'end': end2bib,
                        'txt': txt2bib,
                        'csv': csv2bib,
                        'xlsx': xlsx2bib,
                        'pdf': pdf2bib,
                        'pdf_refs': pdfRefs2bib}

    assert any(search_file.endswith(ext) for ext in importer_scripts.keys())

    # Note: after the search_result_file (non-bib formats) has been loaded
    # for the first time, a corresponding bib_file is saved, which allows
    # for more efficient status checking, tracing, validation
    # This also applies to the pipeline_validation_hooks and is particularly
    # relevant for pdf sources that require long processing times
    corresponding_bib_file = search_file[:search_file.rfind('.')] + '.bib'

    if os.path.exists(corresponding_bib_file) and \
            not '.bib' == search_file[-4]:
        return None

    filetype = search_file[search_file.rfind('.')+1:]
    if 'pdf' == filetype:
        if search_file.endswith('_ref_list.pdf'):
            filetype = 'pdf_refs'
    if filetype in importer_scripts.keys():
        logging.debug(f'Loading {filetype}: {search_file}')
        db = importer_scripts[filetype](search_file_path)
        if db is None:
            logging.error('No records loaded')
            return None
        logging.info(f'Loaded {len(db.entries)} records from {search_file}')
        if corresponding_bib_file != search_file and \
                not '.bib' == search_file[-4]:
            new_file_path = search_file_path.replace('.' + filetype, '.bib')
            with open(new_file_path, 'w') as fi:
                fi.write(bibtexparser.dumps(db))
        return db
    else:
        logging.info('Filetype not recognized: ' + search_file)
        return None


class IteratorEx:
    def __init__(self, it):
        self.it = iter(it)
        self.sentinel = object()
        self.nextItem = next(self.it, self.sentinel)
        self.hasNext = self.nextItem is not self.sentinel

    def next(self):
        ret, self.nextItem = self.nextItem, next(self.it, self.sentinel)
        self.hasNext = self.nextItem is not self.sentinel
        return ret

    def __iter__(self):
        while self.hasNext:
            yield self.next()


current_batch_counter = 0
batch_start = 1
batch_end = 0


def processing_condition(record):
    global current_batch_counter
    global batch_start
    global batch_end

    # Do not count records that have already been imported
    if 'retrieved' != record.get('md_status', 'NA'):
        return False

    if 0 == current_batch_counter:
        batch_start = batch_end + 1

    current_batch_counter += 1
    batch_end += 1

    if current_batch_counter >= BATCH_SIZE:
        current_batch_counter = 0
        return True

    return False


def save_imported_files(repo, bib_db):
    if bib_db is None:
        logging.info('No records imported')
        return False

    if 0 == len(bib_db.entries):
        logging.info('No records imported')
        return False

    utils.save_bib_file(bib_db, MAIN_REFERENCES)
    repo.index.add([SEARCH_DETAILS])
    repo.index.add(get_search_files())
    repo.index.add([MAIN_REFERENCES])

    if not repo.is_dirty():
        logging.info('No new records added to MAIN_REFERENCES')
        return False

    return True


def main(repo, keep_ids):
    saved_args = locals()
    if not keep_ids:
        del saved_args['keep_ids']
    global batch_start
    global batch_end

    utils.reset_log()
    logging.info('Import')
    logging.info(f'Batch size: {BATCH_SIZE}')

    bib_db = BibDatabase()
    record_iterator = IteratorEx(load_all_records())
    for record in record_iterator:
        bib_db.entries.append(record)
        if record_iterator.hasNext:
            if not processing_condition(record):
                continue  # keep appending records
        else:
            processing_condition(record)  # updates counters

        if batch_start > 1:
            logging.info('Continuing batch import started earlier')
        if 0 == batch_end:
            logging.info('No new records')
            break
        if 1 == batch_end:
            logging.info('Importing one record')
        if batch_end != 1:
            logging.info(f'Importing records {batch_start} to {batch_end}')

        pool = mp.Pool(repo_setup.config['CPUS'])
        bib_db.entries = pool.map(import_record, bib_db.entries)
        pool.close()
        pool.join()

        if not keep_ids:
            bib_db = utils.set_IDs(bib_db)

        if save_imported_files(repo, bib_db):
            utils.create_commit(repo, '⚙️ Import search results', saved_args)

    print()
    bib_db.entries = sorted(bib_db.entries, key=lambda d: d['ID'])

    return bib_db

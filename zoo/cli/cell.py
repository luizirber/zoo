import click
from deepdiff import DeepDiff
import json
from progressbar import ProgressBar, UnknownLength
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError
from sourmash_lib import Estimators, signature, signature_json
from uuid import uuid4
from zoo.hash import hash_dict
from zoo.utils import deep_get


'''
Helper functions.
'''


def abort_if_false(ctx, param, value):
    '''http://click.pocoo.org/5/options/#prompting'''
    if not value:
        ctx.abort()


'''
CLI
'''


'''
init
'''


@click.option('--client', default='localhost:27017')
@click.option('--db', required=True)
@click.option('--cell', required=True, help='Cell name.')
@click.argument('file', type=click.Path())
@click.command()
def init(file, client, db, cell):  # load json to mongodb and assign UUID
    '''
    If we write, no file extension needed, if we read, needed to indicate file.
    See also "zoo add ..." (read) vs. "zoo commit" (write).

    Example:

    \b
    $ zoo init --db zika --cell animals zoo/data/cell_a.json
    Initializing data cell.
    Inserted 3 entries into "animals".
    '''
    click.echo('Initializing data cell.')
    c = MongoClient(client)[db][cell]
    inserted = 0
    with open(file, 'r+') as f:
        for line in f:
            d = json.loads(line.strip())
            d['_id'] = str(uuid4())
            c.insert_one(d)
            inserted += 1
    print(inserted, 'entries inserted into cell', '"' + cell + '".')
    print('Primary key assigned to field "_id".')


'''
add
'''


@click.command()
@click.option('--client', default='localhost:27017')
@click.option('--db', required=True)
@click.option('--cell', required=True, help='Cell name.')
@click.option(
    '--primkey', default='_id',
    help='What is the primary key to judge duplicates by? UUID, GenBank?')
@click.argument('file', type=click.File('r+'))
def add(file, client, db, cell, primkey):
    '''Load a data cell.

    An alternative primary key can be specified to insert documents. This
    is useful in the case where the data cell comes from a collaborator
    who uses a different set of UUIDs as we do. In this case, these identifiers
    do not reflect, whether an entry is a duplicate.

    Example:

    \b
    $ zoo add --client localhost:27017 --db zika --cell t5 zoo/data/cell_a.json
    Loading data cell.
    3 documents inserted in collection t5.
    0 duplicates skipped.
    Done.

    \b
    $ zoo add --db zika --cell t5 --primkey genbank.a zoo/data/cell_b.json
    Loading data cell.
    Index created on field "genbank.a".
    1 documents inserted in collection t5.
    3 duplicates skipped.
    Done.
    '''
    click.echo('Loading data cell.')
    c = MongoClient(client)[db][cell]
    inserted = 0
    duplicates = 0
    if primkey == '_id':
        for line in file:
            try:
                c.insert_one(json.loads(line.strip()))
                inserted += 1
            except DuplicateKeyError:
                duplicates += 1
                pass
    else:
        # index primkey if it does not exists yet
        if primkey not in c.index_information():
            c.create_index(primkey, unique=True, name=primkey)
            print('Index created on field', '"' + primkey + '".')
        for line in file:
            d = json.loads(line.strip())
            if c.find_one({primkey: deep_get(d, primkey)}):  # no duplicate
                duplicates += 1
            else:
                c.insert_one(d)
                inserted += 1

    print(
        inserted, 'documents inserted in cell', '"' + cell + '".')
    if duplicates > 0:
        print(duplicates, 'duplicates skipped.\nDone.')


'''
commit
'''


@click.command()
@click.option('--client', default='localhost:27017')
@click.option('--db', required=True)
@click.option(
    '--cell', required=True,
    help='Cell name.')
@click.option(
    '--ksize', default='16,31',
    help='Comma separated list of k-mer sizes. Larger is more specific.')
@click.option('--n', default=1000)
@click.argument(
    'file', type=click.Path())
def commit(file, client, db, cell, ksize, n):
    '''Dump a (mongodb) cursor to a data cell.

    For each document, start a new line in the output.

    file argument: Filename prefix w/o extension.

    \b
    {"_id":"86853586-5e9...
    {"_id":"689e59b8-514...
    {"_id":"6d9bff35-aab...

    This is important bc/ it circumvents the need to hold more than one record
    in memory, both on import and export. Note also that this is the same
    output format as ...

    \b
    $ mongoexport --db foo --collection bar --out bar.json
    ... and can be reimported by
    $ mongoimport --db foo --collection bar2 bar.json

    Example:

    $ zoo commit --db zika --cell survey --n 5 surveytest
    '''
    click.echo('Dumping data cell.')
    db = MongoClient(client)[db]

    # initialize minhash
    ksize = [int(i) for i in ksize.split(',')]
    dk = {k: Estimators(ksize=k, n=n) for k in ksize}

    bar = ProgressBar(max_value=UnknownLength)
    counter = 0
    with open(file + '.json', 'w+') as f:
        for d in db[cell].find():
            counter += 1

            # calculate fresh md5 hash for each record
            _id = d.pop('_id')
            # Neither the primary key (because it is random)
            # nor the checksum should figure in the checksum.
            try:
                del d['md5']
            except KeyError:
                pass
            d['md5'] = hash_dict(d)
            d['_id'] = _id
            f.write(json.dumps(d, indent=None, sort_keys=True) + '\n')

            # update aggregate minhash for collection
            for v in dk.values():
                v.add_sequence(d['sequence'], force=True)

            # update progress bar
            bar.update(counter)

    # save minhash
    for k, v in dk.items():
        dk.update({
            k: signature.SourmashSignature(
                estimator=v, name=cell, email='', filename='')})
    # print('\n', ksize[0], ksize[1], n)

    with open(file + '.zoo', 'w+') as f:
        signature_json.save_signatures_json(
            dk.values(), fp=f, indent=4, sort_keys=True)
    click.echo('\nDone.')


'''
pull
'''


@click.option('--client', default='localhost:27017')
@click.option('--db', required=True)
@click.option('--cell', required=True, help='Cell name.')
@click.argument('file', type=click.File('r+'))
@click.command()
def pull(file, client, db, cell):
    '''
    for each entry in existing database:
    1. calculate fresh md5
    o need to calc new hash or pulled file as commit takes care of that
    2. compare old vs. new, if != drop entry end replace with pulled one
    4. we can assume primary keys same, because we pull changes from existing.
    '''
    print("Updating cell's md5 hashes.")
    c = MongoClient(client)[db][cell]

    bar = ProgressBar(max_value=UnknownLength)

    counter = 0
    nochange = 0
    replaced = 0
    inserted = 0

    for line in file:
        d_new = json.loads(line.strip())

        _id_new = d_new['_id']
        md5_new = d_new['md5']

        d_old = c.find_one({'_id': _id_new}, {'_id': 0, 'md5': 0})

        if not d_old:  # new entry
            c.insert_one(d_new)
            inserted += 1
            counter += 1
        else:  # update and check md5
            md5_old = hash_dict(d_old)

            if md5_new == md5_old:  # no need to update
                nochange += 1
                counter += 1
                continue
            else:
                c.find_one_and_replace({'_id': _id_new}, d_new)
                replaced += 1
                counter += 1
        bar.update(counter)
    print('\n')
    for k, v in {
            'unchanged': nochange,
            'replaced': replaced,
            'inserted': inserted
            }.items():
        if v > 0:
            print(v, 'entries', k + '.')


'''
drop
'''


@click.option('--client', default='localhost:27017')
@click.option('--db', required=True)
@click.option('--cell', required=True, help='Cell name.')
@click.option('--force', is_flag=True, callback=abort_if_false,
              expose_value=False,
              prompt='Sure to drop entire cell?')
@click.command()
def drop(client, db, cell):  # cell
    '''Delete a cell.

    If a cell did not exist, it is dropped nevertheless. Ask your favourite
    philosopher what it means to delete something that did not exist.

    Example:

    \b
    $ zoo drop --db zika --cell survey
    Are you sure you want to drop the db? [y/N]: y
    Dropped cell "animals" from database "zika".

    \b
    $ zoo drop --db zika --cell survey --force  # no confirmation
    Dropped cell "animals" from database "zika".
    '''
    c = MongoClient(client)[db][cell]
    c.drop()
    print('Dropped cell', '"' + cell + '"', 'from database', '"' + db + '".')


'''
destroy
'''


@click.option('--client', default='localhost:27017')
@click.option('--db', required=True)
@click.option('--force', is_flag=True, callback=abort_if_false,
              expose_value=False,
              prompt='Sure to drop entire zoo?')
@click.command()
def destroy(client, db):  # drop database entirely
    MongoClient(client).drop_database(db)
    print('Dropped database', '"' + db + '".')


'''
diff
'''


@click.option('--client', default='localhost:27017')
@click.option('--db', required=True)
@click.option('--cell', required=True, help='Cell name.')
@click.option('--out', default='diff.json')
@click.argument('file', type=click.File('r+'))
@click.command()
def diff(client, db, cell, out, file):
    '''
    Example:

    \b
    zoo add --db diff --cell mock tests/cell_a.json
    zoo diff --db diff --cell mock --out diff.json tests/cell_b.json
    cat diff.json
    '''

    c = MongoClient(client)[db][cell]

    print('Writing diff.')
    with open(out, 'w+') as outfile:
        for line in file:
            old = json.loads(line.strip())
            _id = old['_id']
            new = c.find_one({'_id': _id})
            diff = DeepDiff(
                new, old,  # note order of new, old
                ignore_order=True,
                verbose_level=2)
            if diff:
                diff['_id'] = _id
                outfile.write(diff.json)
                outfile.write('\n')
    print('Done.')


'''
status
'''


@click.option('--client', default='localhost:27017')
@click.option('--db', required=True)
@click.option('--cell', required=True, help='Cell name.')
@click.option(
    '--example', required=False, help='Include example document?',
    is_flag=True)
@click.command()
def status(client, db, cell, example):
    '''
    \b
    - list cells, num_entries
    - verbose: find_one() in each cell but truncate sequence field before print
    - include .zoo metadata in the report in the future

    Example:

    \b
    zoo status --db diff --cell mock --example
    '''
    c = MongoClient(client)[db][cell]
    print(c.count(), 'documents.\n')
    if example:
        print('Example:')
        print(json.dumps(c.find_one(), indent=2))
        print()


@click.command()
def validate():
    print('Trying.')

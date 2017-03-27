import click
import json
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError


@click.command()
@click.option('--client', default='localhost:27017')
@click.option('--db', default='test')
@click.option('--cell', default='test')
@click.argument('infile', type=click.File('r+'), nargs=-1)
def add(infile, client, db, cell):
    '''Load a data cell.

    Example:

    zoo --client localhost:27017 --db zika --cell survey survey.json
    zoo --client localhost:27017 --db zika --cell survey *
    '''
    click.echo('Loading data cell.')
    c = MongoClient(client)[db][cell]
    for i in infile:
        for line in i:
            try:
                c.insert_one(json.loads(line.strip()))
            except DuplicateKeyError:
                print('Duplicate key, loading aborted.')
                return
        print(c.count(), 'documents inserted in collection', cell + '.')


@click.command()
@click.option('--client', default='localhost:27017')
@click.option('--db', default='test')
@click.option('--collection', default='test')
@click.argument('outfile', type=click.File('w+'))
def commit(outfile, client, db, collection):
    '''Dump a (mongodb) cursor to a data cell.

    For each document, start a new line in the output.

    {"_id":"86853586-5e9...
    {"_id":"689e59b8-514...
    {"_id":"6d9bff35-aab...

    This is important bc/ it circumvents the need to hold more than one record
    in memory, both on import and export. Note also that this is the same
    output format as ...

    $ mongoexport --db foo --collection bar --out bar.json
    ... and can be reimported by
    $ mongoimport --db foo --collection bar2 bar.json
    '''
    click.echo('Dumping data cell.')
    c = MongoClient(client)[db][collection]
    for i in c.find():
        outfile.write(json.dumps(i) + '\n')  # same as zoo.io.dump_json


@click.command()
def diff(outfile, client, db, collection):
    pass


@click.command()
def pull():
    print('Trying.')



from hashlib import md5
import json

with open(zoo.get_data('cell_a.json'), 'r+') as file:
    hashmap = {}
    for line in file:
        d = json.loads(line)
        _id = d.pop("_id")

        # hash line (all but primary key)
        h = md5()
        h.update(json.dumps(d, sort_keys=True).encode('utf-8'))
        value = h.hexdigest()
        hashmap[_id] = value
        # It is important that keys be sorted, as Python does not enforce this.


def hash_document(d):
    '''md5 hash the JSON string representation of a dict w/o key "_id"'''
    _id = d.pop('_id')
    h = md5()
    h.update(json.dumps(d, sort_keys=True).encode('utf-8'))
    value = h.hexdigest()
    return _id, value



























def random_draw(collection, match, n):
    '''
    In: collection, match dictionary (i.e. the filter), sample size n
    Out: documents of samples as database cursor (i.e. generator)

    Usage:
    from pymongo import MongoClient

    client = MongoClient("localhost:27017")
    db = client["zoo"]
    collection = db.get_collection('influenza_a_virus')

    match = {
        'annotation.name': 'HA',
        'metadata.host': 'Avian',
        'metadata.date.y': {'$gte': 2000}
    }

    gen = random_draw(collection, match, n)
    next(gen)
    # GQ377055
    '''
    sample = {'size': n}
    pipeline = [{'$match': match}, {'$sample': sample}]
    query = collection.aggregate(pipeline)
    return query

import logging
import redis

r = redis.StrictRedis(host='localhost', port=6379, db=0)

logger = logging.getLogger(__name__)


# FIXME: Rename to memoize_zset?
def save_to_zset(key_pattern: str):
    def wrap(f):
        def wrapped_function(pk, start: int, end: int):
            key = key_pattern.format(pk)
            if not r.exists(key):
                logger.debug('Heat up cache for {}'.format(key))
                result = f(pk, start, end)

                if not result:
                    logger.debug('Nothing to cache. Key is {}'.format(key))
                    return []

                if len(result) % 2:
                    logger.error('Invalid result size for {}. Size is {}'.format(key, len(result)))
                    return []

                r.zadd(key, *result)
            result = r.zrevrange(key, start, end)
            return [int(it) for it in result]
        return wrapped_function
    return wrap


def memoize_list(key_pattern: str):
    def wrap(f):
        def wrapped_function(pk: int, start: int, end: int):
            key = key_pattern.format(pk)
            if not r.exists(key):
                logger.debug('Heat up cache for %s', key)
                result = f(pk, start, end)

                if not result:
                    logger.debug('Nothing to cache for %s key', key)
                    return []

                for it in result:
                    r.lpush(key, it)

            cached = r.lrange(key, start, end)
            return (int(it) for it in cached)
        return wrapped_function
    return wrap

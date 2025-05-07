from collections import OrderedDict
import threading

class LRUCache:
    def __init__(self, cache_size):
        self.cache = OrderedDict()
        self.cache_size = cache_size
        self.lock = threading.Lock()


    def get(self, key):
        with self.lock:
            if key not in self.cache:
                return None
            value = self.cache.pop(key)
            self.cache[key] = value
            return value
        

    def put(self, key, value):
        with self.lock:
            if key in self.cache:
                self.cache.pop(key)
            elif len(self.cache) >= self.cache_size:
                self.cache.popitem(last=False)
            self.cache[key] = value


    def invalidate(self, key):
        with self.lock:
            self.cache.pop(key, None)

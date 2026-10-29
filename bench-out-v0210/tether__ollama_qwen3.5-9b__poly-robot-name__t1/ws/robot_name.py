import random
import string

class Robot:
    _name_pool = set()
    
    def __init__(self):
        self.name = self._generate_name()
    
    def _generate_name(self):
        while True:
            name = ''.join(random.choices(string.ascii_uppercase, k=2)) + \
                    ''.join(random.choices(string.digits, k=3))
            if name not in self._name_pool:
                self._name_pool.add(name)
                return name
    
    def reset(self):
        self.name = self._generate_name()
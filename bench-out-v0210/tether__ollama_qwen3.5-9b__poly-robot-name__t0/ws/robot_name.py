import random
import string

class Robot:
    _name_counter = 0
    _used_names = set()
    
    def __init__(self):
        if not hasattr(self, '_name'):
            self._name = self._generate_name()
    
    def _generate_name(self):
        while True:
            name = ''.join(random.choices(string.ascii_uppercase, k=2)) + \
                    ''.join(random.choices(string.digits, k=3))
            if name not in self._used_names:
                self._used_names.add(name)
                return name
    
    @property
    def name(self):
        return self._name
    
    def reset(self):
        self._name = self._generate_name()
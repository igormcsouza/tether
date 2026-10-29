- `find_user`: SQL injection vulnerability - user-supplied `name` parameter is directly concatenated into the SQL query string without sanitization or parameterized queries.

- `add_tags`: Mutable default argument bug - using `tags=[]` as a default argument means all function calls share the same list object, causing unexpected accumulation of data across calls.

- `read_config`: Path traversal vulnerability - user-supplied `path` parameter is used directly in `open(path)` without validation, allowing attackers to read arbitrary files outside the intended configuration directory.
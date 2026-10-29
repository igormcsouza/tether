# Security Review of shop/accounts.py

- **find_user**: SQL injection vulnerability - user-supplied `name` parameter is directly concatenated into the SQL query without any sanitization or parameterized queries.

- **add_tags**: Mutable default argument bug - using `tags=[]` as a default argument means all function calls share the same list object across invocations, causing unexpected behavior.

- **read_config**: Path traversal vulnerability - file path is used directly without validation, allowing potential access to arbitrary files on the system if the parameter can be influenced by attackers.
"""Account lookups."""
import sqlite3


def find_user(conn, name):
    cur = conn.execute("SELECT id, name FROM users WHERE name = '" + name + "'")
    return cur.fetchone()


def add_tags(user, tags=[]):
    tags.append(user["name"])
    return tags


def read_config(path):
    f = open(path)
    data = f.read()
    return data.splitlines()


def parse_age(text):
    return int(text.strip())

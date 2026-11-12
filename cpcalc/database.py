"""The built-in database (one JSON file). Each compound has a list of records;
a record is either a single value ("value") or a temperature curve ("points")."""
import json
import os

PATH = os.path.join(os.path.dirname(__file__), "data", "database.json")
_CACHE = {}


def load_database(path=None):
    path = path or PATH
    if path not in _CACHE:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        _CACHE[path] = make_db(raw["components"], raw.get("_about", ""))
    return _CACHE[path]


def make_db(components, about=""):
    """Index components by id, alias, CAS and name (all lower case)."""
    db = {"components": {}, "index": {}, "about": about}
    for cid, entry in components.items():
        add_component(db, cid, entry)
    return db


def add_component(db, cid, entry):
    cid = cid.strip().lower()
    db["components"][cid] = entry
    for name in [cid, entry.get("name", ""), entry.get("cas", "")] + entry.get("aliases", []):
        if name:
            db["index"].setdefault(str(name).strip().lower(), cid)


def with_extra(db, extra):
    """A copy of the database plus extra components (e.g. found with the UI's lookup)."""
    if not extra:
        return db
    new = {"components": dict(db["components"]), "index": dict(db["index"]), "about": db["about"]}
    for cid, entry in extra.items():
        add_component(new, cid, entry)
    return new


def find(db, name):
    """Database id of a compound (by id, name, alias or CAS), or None."""
    if db is None or name is None:
        return None
    return db["index"].get(str(name).strip().lower())


def entry(db, name):
    cid = find(db, name)
    return db["components"][cid] if cid else None


def records(db, name, key):
    e = entry(db, name)
    return [r for r in (e["records"] if e else []) if r["key"] == key]


def choices(db):
    """Sorted list of database ids for drop-down lists."""
    return sorted(db["components"])


def label(db, cid):
    e = entry(db, cid)
    if not e:
        return cid
    return "%s (%s)" % (e.get("name", cid), e.get("cas", ""))

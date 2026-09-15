"""Reading positions, recent books and settings, in one JSON file."""

import json
import os

from . import paths


class Library:
    def __init__(self):
        self.path = paths.data_dir() / "library.json"
        try:
            with open(self.path, encoding="utf-8") as fh:
                self.data = json.load(fh)
        except (OSError, ValueError):
            self.data = {}
        self.data.setdefault("books", {})

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.data, fh, indent=1)
        os.replace(tmp, self.path)

    def book(self, path):
        return self.data["books"].get(path, {})

    def remember(self, path, **fields):
        entry = self.data["books"].setdefault(path, {})
        entry.update(fields)

    def recent(self, limit=8):
        books = [(p, b) for p, b in self.data["books"].items()
                 if os.path.exists(p)]
        books.sort(key=lambda pb: pb[1].get("opened", 0), reverse=True)
        return books[:limit]

    def setting(self, key, default):
        return self.data.get(key, default)

    def set_setting(self, key, value):
        self.data[key] = value

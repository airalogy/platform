"""Read literal Alembic ancestry without importing or executing migrations."""

import ast
import re
import sys
from pathlib import Path


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", value
    ):
        raise ValueError("Migration identifiers must be bounded literal strings")
    return value


def declarations(source, filename):
    values = {}
    for node in ast.parse(source, filename=filename).body:
        if isinstance(node, ast.AnnAssign):
            targets = [node.target]
        elif isinstance(node, ast.Assign):
            targets = node.targets
        else:
            continue
        for target in targets:
            if not isinstance(target, ast.Name) or target.id not in {
                "revision", "down_revision", "depends_on"
            }:
                continue
            if target.id in values or len(targets) != 1:
                raise ValueError(f"Ambiguous {target.id} declaration in {filename}")
            try:
                values[target.id] = ast.literal_eval(node.value)
            except (ValueError, TypeError) as error:
                raise ValueError(f"{target.id} must be a literal in {filename}") from error
    for required in ("revision", "down_revision"):
        if required not in values:
            raise ValueError(f"Missing {required} declaration in {filename}")
    if values.get("depends_on") is not None:
        raise ValueError(f"Release metadata does not yet support depends_on in {filename}")
    revision = identifier(values["revision"])
    parent = values["down_revision"]
    if parent is None:
        parents = ()
    elif isinstance(parent, (tuple, list)):
        parents = parent
    else:
        parents = (parent,)
    parents = tuple(identifier(value) for value in parents)
    if len(set(parents)) != len(parents):
        raise ValueError(f"Duplicate migration parents in {filename}")
    return revision, parents


def migration_head(directory):
    ancestry = {}
    for file in sorted(directory.glob("*.py")):
        if file.name == "__init__.py":
            continue
        if file.is_symlink() or not file.is_file():
            raise ValueError(f"Migration source must be a regular file: {file.name}")
        revision, parents = declarations(file.read_text(encoding="utf-8"), file.name)
        if revision in ancestry:
            raise ValueError(f"Duplicate migration revision: {revision}")
        ancestry[revision] = parents
    parents = {parent for values in ancestry.values() for parent in values}
    missing = parents - ancestry.keys()
    if missing:
        raise ValueError(f"Missing migration parent: {', '.join(sorted(missing))}")
    heads = sorted(ancestry.keys() - parents)
    if len(heads) != 1:
        raise ValueError(f"Expected one Alembic head, found {len(heads)}: {', '.join(heads)}")
    visited, visiting = set(), set()

    def visit(revision):
        if revision in visiting:
            raise ValueError("Migration ancestry contains a cycle")
        if revision in visited:
            return
        visiting.add(revision)
        for parent in ancestry[revision]:
            visit(parent)
        visiting.remove(revision)
        visited.add(revision)

    visit(heads[0])
    if visited != ancestry.keys():
        raise ValueError("Migration ancestry contains disconnected revisions or cycles")
    return heads[0]


if __name__ == "__main__":
    try:
        print(migration_head(Path(sys.argv[1])))
    except (ValueError, SyntaxError, OSError) as error:
        sys.exit(str(error))

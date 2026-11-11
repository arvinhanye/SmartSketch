"""Optional OPT-05 guard: run ``.venv/bin/python -m pytest tests/tooling/test_backend_layering.py``.

This is a syntax guard, not a type checker: it recognizes direct imported classes,
module aliases and ``from_settings`` factories, not dynamic getattr/re-exports.
Services may not embed Cypher or call ``.execute``. Any legitimate non-database
execute call needs its own exact, explained exception; no file-wide exemptions.
Repository data classes count as construction, while exception classes do not.
"""

from __future__ import annotations

import ast
import builtins
import importlib.util
import re
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "src/backend/app"
CYPHER = re.compile(r"\b(?:MATCH|MERGE)\s*\(", re.IGNORECASE)
# Keys are (app-relative path, enclosing function/class, rule, full expression).
# Counts prevent a second identical call from inheriting an existing exception.
# OPT-05 deliberately leaves these older API dependency factories for follow-up.
LEGACY_CONSTRUCTION = {
    ("api/graph.py", "graph_reader", "repository-construction",
     "GraphReader(Neo4jRepository.from_settings(request.app.state.settings))"): 1,
    ("api/graph.py", "graph_reader", "repository-construction",
     "Neo4jRepository.from_settings(request.app.state.settings)"): 1,
    ("api/graph_nodes.py", "node_store", "repository-construction",
     "DraftNodeStore(Neo4jRepository.from_settings(request.app.state.settings))"): 1,
    ("api/graph_nodes.py", "node_store", "repository-construction",
     "Neo4jRepository.from_settings(request.app.state.settings)"): 1,
    ("api/relations.py", "relation_store", "repository-construction",
     "DraftRelationStore(Neo4jRepository.from_settings(request.app.state.settings))"): 1,
    ("api/relations.py", "relation_store", "repository-construction",
     "Neo4jRepository.from_settings(request.app.state.settings)"): 1,
    ("api/versions.py", "publish_context", "repository-construction",
     "Neo4jRepository.from_settings(settings)"): 1,
}


def _name(node: ast.AST, aliases: dict[str, str]) -> str:
    if isinstance(node, ast.Name):
        return aliases.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        return f"{_name(node.value, aliases)}.{node.attr}"
    return ""


def _imports(tree: ast.AST, module: str) -> dict[str, str]:
    aliases = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                aliases[item.asname or item.name.split(".")[0]] = (
                    item.name if item.asname else item.name.split(".")[0]
                )
        elif isinstance(node, ast.ImportFrom):
            source = node.module or ""
            if node.level:
                source = importlib.util.resolve_name(
                    "." * node.level + source, module.rpartition(".")[0]
                )
            for item in node.names:
                aliases[item.asname or item.name] = f"{source}.{item.name}"
    return aliases


def _repository_classes(sources: dict[str, str]) -> set[str]:
    """Read class declarations without importing storage or opening databases."""
    classes = {}
    for module, source in sources.items():
        tree = ast.parse(source)
        aliases = _imports(tree, module)
        aliases.update({node.name: f"{module}.{node.name}" for node in tree.body if isinstance(node, ast.ClassDef)})
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                classes[f"{module}.{node.name}"] = [_name(base, aliases) for base in node.bases]
    exceptions = {
        name for name, value in vars(builtins).items()
        if isinstance(value, type) and issubclass(value, BaseException)
    }
    exceptions |= {f"builtins.{name}" for name in exceptions}
    while True:
        inherited = {name for name, bases in classes.items() if set(bases) & exceptions}
        if inherited <= exceptions:
            return set(classes) - exceptions
        exceptions |= inherited


class _Scan(ast.NodeVisitor):
    def __init__(self, source: str, path: str, repository_classes: set[str]):
        self.tree = ast.parse(source)
        self.path = path
        self.aliases = _imports(self.tree, "app." + path.removesuffix(".py").replace("/", "."))
        self.repository_classes = repository_classes
        self.scope: list[str] = []
        self.findings: list[tuple[tuple[str, str, str, str], int]] = []

    def record(self, rule: str, node: ast.AST) -> None:
        key = (self.path, ".".join(self.scope) or "<module>", rule, ast.unparse(node))
        self.findings.append((key, node.lineno))

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    visit_AsyncFunctionDef = visit_FunctionDef
    visit_ClassDef = visit_FunctionDef

    def visit_Expr(self, node: ast.Expr) -> None:
        # Docstrings (including attribute documentation) have no runtime query use.
        if not isinstance(node.value, ast.Constant) or not isinstance(node.value.value, str):
            self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if self.path.startswith("services/") and isinstance(node.value, str) and CYPHER.search(node.value):
            self.record("cypher", node)

    def visit_Call(self, node: ast.Call) -> None:
        if self.path.startswith("services/") and isinstance(node.func, ast.Attribute) and node.func.attr == "execute":
            self.record("execute", node)
        if self.path.startswith("api/"):
            target = _name(node.func, self.aliases).removesuffix(".from_settings")
            if target in self.repository_classes:
                self.record("repository-construction", node)
        self.generic_visit(node)

    def run(self) -> list[tuple[tuple[str, str, str, str], int]]:
        self.visit(self.tree)
        return self.findings


def _check_baseline(findings, allowed) -> None:
    actual = Counter(key for key, _ in findings)
    expected = Counter(allowed)
    added, stale = actual - expected, expected - actual
    lines = {key: line for key, line in findings}
    messages = [
        f"{path}:{lines[key]} [{scope}] {rule} (+{count}): {expression}"
        for key, count in sorted(added.items())
        for path, scope, rule, expression in [key]
    ]
    messages += [f"Remove stale exception ({count}): {key}" for key, count in sorted(stale.items())]
    assert not messages, "Backend layering violations:\n" + "\n".join(messages)


def test_backend_layering_has_no_new_or_stale_exceptions() -> None:
    repository_classes = _repository_classes({
        "app." + str(path.relative_to(APP).with_suffix("")).replace("/", "."): path.read_text(encoding="utf-8")
        for path in (APP / "repositories").rglob("*.py")
    })
    findings = []
    for directory in ("api", "services"):
        paths = sorted((APP / directory).rglob("*.py"))
        assert paths, f"No Python files found in {directory}"
        for path in paths:
            findings.extend(_Scan(path.read_text(encoding="utf-8"), path.relative_to(APP).as_posix(), repository_classes).run())
    _check_baseline(findings, LEGACY_CONSTRUCTION)


@pytest.mark.parametrize("imports, expression", [
    ("from app.repositories.neo4j import Neo4jRepository as Repo", "Repo(settings)"),
    ("from app.repositories.neo4j import Neo4jRepository as Repo", "Repo.from_settings(settings)"),
    ("import app.repositories.neo4j as graph", "graph.Neo4jRepository.from_settings(settings)"),
    ("from app.repositories import neo4j as graph", "graph.Neo4jRepository(settings)"),
    ("import app.repositories.neo4j", "app.repositories.neo4j.Neo4jRepository(settings)"),
    ("from ..repositories.neo4j import Neo4jRepository", "Neo4jRepository(settings)"),
])
def test_repository_construction_resolves_import_aliases(imports, expression) -> None:
    found = _Scan(f"{imports}\ndef factory():\n    return {expression}\n", "api/example.py",
                  {"app.repositories.neo4j.Neo4jRepository"}).run()
    assert [(key[1], key[2], key[3]) for key, _ in found] == [
        ("factory", "repository-construction", expression)
    ]


def test_repository_types_and_exceptions_are_allowed_but_data_construction_is_not() -> None:
    classes = _repository_classes({"app.repositories.example": """
from dataclasses import dataclass
class RepositoryError(RuntimeError): pass
class ConnectionError(RepositoryError): pass
class Repository: pass
@dataclass
class Record: value: str
"""})
    source = """
from app.repositories.example import Repository, Record, ConnectionError
def get_record(repo: Repository) -> Record:
    if isinstance(repo, Repository):
        raise ConnectionError()
    return Record("value")
"""
    found = _Scan(source, "api/example.py", classes).run()
    assert [key[3] for key, _ in found] == ["Record('value')"]


def test_service_queries_ignore_comments_and_docstrings_but_scan_nested_and_f_strings() -> None:
    source = '''
"""Example MATCH (n), database.execute(query)."""
# MATCH (n); database.execute(query)
def service(database):
    """MERGE (n); database.execute(query)."""
    query = f"MATCH (n:{label}) RETURN n"
    database.execute(query)
    async def nested():
        return "merge (n)"
'''
    found = _Scan(source, "services/nested/example.py", set()).run()
    assert Counter((key[1], key[2]) for key, _ in found) == Counter({
        ("service", "cypher"): 1,
        ("service", "execute"): 1,
        ("service.nested", "cypher"): 1,
    })


def test_exact_non_database_execute_exception_does_not_allow_new_calls() -> None:
    # An intentional command executor would get this exact key and a reason;
    # no such service calls exist today, so the production allowlist has none.
    source = "def run(command):\n    command.execute()\n"
    found = _Scan(source, "services/commands.py", set()).run()
    allowed = {found[0][0]: 1}
    _check_baseline(found, allowed)
    with pytest.raises(AssertionError, match=r"execute \(\+1\)"):
        _check_baseline(found + found, allowed)
    with pytest.raises(AssertionError, match="Remove stale exception"):
        _check_baseline([], allowed)

"""Deterministic, non-executing Python repository analysis for ASM.

This first coding subsystem indexes syntax and relationships. It deliberately
never imports or executes project code.
"""
from __future__ import annotations

import ast
import hashlib
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

DEFAULT_EXCLUDES = {
    ".git", ".hg", ".svn", ".venv", "venv", "env", "__pycache__",
    "node_modules", "site-packages", "dist", "build", ".tox", ".mypy_cache",
}


@dataclass(frozen=True)
class Diagnostic:
    code: str
    severity: str
    message: str
    path: str
    line: int | None = None
    column: int | None = None


@dataclass
class Symbol:
    name: str
    qualified_name: str
    kind: str
    line: int
    end_line: int | None
    signature: str | None = None
    docstring: str | None = None


@dataclass
class FileReport:
    path: str
    sha256: str
    bytes: int
    lines: int
    imports: list[str] = field(default_factory=list)
    local_imports: list[str] = field(default_factory=list)
    symbols: list[Symbol] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)


@dataclass
class RepositoryReport:
    root: str
    files: list[FileReport]
    dependency_edges: list[tuple[str, str]]
    diagnostics: list[Diagnostic]
    scanned_files: int
    skipped_files: int
    total_bytes: int
    fingerprint: str

    def to_dict(self) -> dict:
        return asdict(self)

    def summary(self) -> dict:
        return {
            "root": self.root,
            "scanned_files": self.scanned_files,
            "skipped_files": self.skipped_files,
            "total_bytes": self.total_bytes,
            "symbols": sum(len(f.symbols) for f in self.files),
            "imports": sum(len(f.imports) for f in self.files),
            "dependency_edges": len(self.dependency_edges),
            "diagnostics": len(self.diagnostics),
            "fingerprint": self.fingerprint,
        }


class _Visitor(ast.NodeVisitor):
    def __init__(self, path: str):
        self.path = path
        self.symbols: list[Symbol] = []
        self.imports: list[str] = []
        self.calls: list[str] = []
        self.scope: list[str] = []

    def _signature(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
        try:
            return ast.unparse(node.args)
        except Exception:
            return "(...)"

    def visit_FunctionDef(self, node: ast.FunctionDef):
        qn = ".".join(self.scope + [node.name])
        self.symbols.append(Symbol(node.name, qn, "function", node.lineno,
                                   getattr(node, "end_lineno", None), self._signature(node),
                                   ast.get_docstring(node)))
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node: ast.ClassDef):
        qn = ".".join(self.scope + [node.name])
        self.symbols.append(Symbol(node.name, qn, "class", node.lineno,
                                   getattr(node, "end_lineno", None), None,
                                   ast.get_docstring(node)))
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def visit_Import(self, node: ast.Import):
        self.imports.extend(alias.name for alias in node.names)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        prefix = "." * node.level + (node.module or "")
        self.imports.append(prefix)

    def visit_Call(self, node: ast.Call):
        name = _dotted_name(node.func)
        if name:
            self.calls.append(name)
        self.generic_visit(node)


def _dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return None


class CodebaseAnalyzer:
    """Scan Python source into a stable, JSON-serializable structural index."""

    def __init__(self, max_files: int = 5000, max_file_bytes: int = 1_000_000,
                 max_total_bytes: int = 50_000_000, excludes: Iterable[str] = ()):
        if min(max_files, max_file_bytes, max_total_bytes) <= 0:
            raise ValueError("scan limits must be positive")
        self.max_files = max_files
        self.max_file_bytes = max_file_bytes
        self.max_total_bytes = max_total_bytes
        self.excludes = DEFAULT_EXCLUDES | set(excludes)

    def scan(self, root: str | Path) -> RepositoryReport:
        base = Path(root).expanduser().resolve(strict=True)
        if not base.is_dir():
            raise NotADirectoryError(str(base))
        py_files: list[Path] = []
        skipped = 0
        for current, dirs, names in os.walk(base, followlinks=False):
            dirs[:] = sorted(d for d in dirs if d not in self.excludes and not (Path(current) / d).is_symlink())
            for name in sorted(names):
                path = Path(current) / name
                if path.suffix == ".py" and not path.is_symlink():
                    py_files.append(path)
        py_files.sort(key=lambda p: p.relative_to(base).as_posix())
        if len(py_files) > self.max_files:
            skipped += len(py_files) - self.max_files
            py_files = py_files[:self.max_files]

        reports: list[FileReport] = []
        total = 0
        for path in py_files:
            try:
                size = path.stat().st_size
                if size > self.max_file_bytes or total + size > self.max_total_bytes:
                    skipped += 1
                    continue
                raw = path.read_bytes()
                total += len(raw)
                rel = path.relative_to(base).as_posix()
                reports.append(self._analyze_file(rel, raw))
            except (OSError, UnicodeError) as exc:
                skipped += 1
                reports.append(FileReport(path.relative_to(base).as_posix(), "", 0, 0,
                                          diagnostics=[Diagnostic("ASM-CODE-IO", "warning", str(exc),
                                                                  path.relative_to(base).as_posix())]))

        module_map = self._module_map(reports)
        edges: set[tuple[str, str]] = set()
        diagnostics: list[Diagnostic] = []
        for report in reports:
            diagnostics.extend(report.diagnostics)
            source_module = self._path_module(report.path)
            for imported in report.imports:
                target = self._resolve_import(imported, source_module, report.path)
                if target in module_map and target != source_module:
                    edges.add((report.path, module_map[target]))
                elif target and self._looks_local(target, module_map):
                    diagnostics.append(Diagnostic("ASM-CODE-IMPORT", "warning",
                        f"Possible unresolved local import: {imported}", report.path))
        edges_list = sorted(edges)
        digest = hashlib.sha256()
        for report in reports:
            digest.update(report.path.encode()); digest.update(report.sha256.encode())
        return RepositoryReport(str(base), reports, edges_list, diagnostics,
                                len(reports), skipped, total, digest.hexdigest())

    def analyze_file(self, source: str, path: str = "<memory>") -> FileReport:
        return self._analyze_file(path, source.encode("utf-8"))

    def _analyze_file(self, rel: str, raw: bytes) -> FileReport:
        sha = hashlib.sha256(raw).hexdigest()
        try:
            source = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            return FileReport(rel, sha, len(raw), 0,
                diagnostics=[Diagnostic("ASM-CODE-ENCODING", "error", str(exc), rel)])
        lines = source.count("\n") + (1 if source else 0)
        try:
            tree = ast.parse(source, filename=rel)
        except SyntaxError as exc:
            return FileReport(rel, sha, len(raw), lines,
                diagnostics=[Diagnostic("ASM-CODE-SYNTAX", "error", exc.msg, rel, exc.lineno, exc.offset)])
        visitor = _Visitor(rel)
        visitor.visit(tree)
        return FileReport(rel, sha, len(raw), lines, sorted(set(visitor.imports)), [],
                          visitor.symbols, sorted(set(visitor.calls)), [])

    @staticmethod
    def _path_module(path: str) -> str:
        p = Path(path).with_suffix("")
        parts = list(p.parts)
        if parts and parts[-1] == "__init__":
            parts.pop()
        return ".".join(parts)

    def _module_map(self, reports: list[FileReport]) -> dict[str, str]:
        result = {}
        for report in reports:
            mod = self._path_module(report.path)
            if mod:
                result[mod] = report.path
        return result

    @staticmethod
    def _resolve_import(imported: str, source_module: str, path: str) -> str:
        if not imported.startswith("."):
            return imported
        level = len(imported) - len(imported.lstrip("."))
        suffix = imported[level:]
        package = source_module.split(".")[:-1]
        if Path(path).name == "__init__.py":
            package = source_module.split(".")
        keep = max(0, len(package) - (level - 1))
        prefix = package[:keep]
        return ".".join(prefix + ([suffix] if suffix else []))

    @staticmethod
    def _looks_local(target: str, module_map: dict[str, str]) -> bool:
        if not target:
            return False
        top = target.split(".", 1)[0]
        return any(m == top or m.startswith(top + ".") for m in module_map)

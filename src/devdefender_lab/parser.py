from __future__ import annotations

import ast
from pathlib import Path

from tree_sitter import Language, Parser
import tree_sitter_python

from devdefender_lab.models import CodeEdge, CodeGraphPayload, CodeNode


def _make_python_parser() -> Parser:
    parser = Parser()
    parser.language = Language(tree_sitter_python.language())
    return parser


def parse_python_repo(repo_path: Path) -> CodeGraphPayload:
    parser = _make_python_parser()
    nodes: list[CodeNode] = []
    edges: list[CodeEdge] = []

    for file_path in sorted(repo_path.rglob("*.py")):
        source = file_path.read_text(encoding="utf-8")
        parser.parse(source.encode("utf-8"))
        module = ast.parse(source, filename=str(file_path))
        rel_file = file_path.relative_to(repo_path).as_posix()
        import_nodes = _extract_imports(module, rel_file)
        function_nodes, call_edges = _extract_functions_and_calls(module, rel_file)
        nodes.extend(import_nodes)
        nodes.extend(function_nodes)
        edges.extend(call_edges)

    return CodeGraphPayload(nodes=nodes, edges=edges)


def _extract_imports(module: ast.Module, rel_file: str) -> list[CodeNode]:
    nodes: list[CodeNode] = []
    for statement in module.body:
        if isinstance(statement, ast.Import):
            for alias in statement.names:
                nodes.append(
                    CodeNode(
                        id=f"{rel_file}:import:{alias.name}",
                        kind="import",
                        name=alias.name,
                        file=rel_file,
                        line=statement.lineno,
                    )
                )
        elif isinstance(statement, ast.ImportFrom):
            module_name = statement.module or ""
            for alias in statement.names:
                imported = f"{module_name}.{alias.name}".strip(".")
                nodes.append(
                    CodeNode(
                        id=f"{rel_file}:import:{imported}",
                        kind="import",
                        name=imported,
                        file=rel_file,
                        line=statement.lineno,
                    )
                )
    return nodes


def _extract_functions_and_calls(module: ast.Module, rel_file: str) -> tuple[list[CodeNode], list[CodeEdge]]:
    nodes: list[CodeNode] = []
    edges: list[CodeEdge] = []
    local_functions = {
        node.name
        for node in ast.walk(module)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    for node in ast.walk(module):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        source_id = f"{rel_file}:function:{node.name}"
        nodes.append(
            CodeNode(
                id=source_id,
                kind="function",
                name=node.name,
                file=rel_file,
                line=node.lineno,
            )
        )
        for child in ast.walk(node):
            if not isinstance(child, ast.Call):
                continue
            call_name = _call_name(child.func)
            if call_name in local_functions:
                edges.append(
                    CodeEdge(
                        source=source_id,
                        target=f"{rel_file}:function:{call_name}",
                        kind="CALLS",
                    )
                )
    return nodes, edges


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""

#!/usr/bin/env python3
"""
cfg_analysis.py  —  Drop this ONE file into your project root (next to app.py).

Run:
    python cfg_analysis.py file1.py file2.py file3.py
    python cfg_analysis.py file1.py file2.py --dot-dir out/   # also saves .dot graphs
    python cfg_analysis.py file1.py                            # single file summary
"""

# ─────────────────────────────────────────────────────────────────────────────
#  stdlib only — no new pip installs needed
# ─────────────────────────────────────────────────────────────────────────────
import argparse
import ast
import itertools
import math
import os
import sys
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# ─────────────────────────────────────────────────────────────────────────────
#  Re-use your existing modules (unchanged)
# ─────────────────────────────────────────────────────────────────────────────
from core.parser import get_ast_tree
from core.tokenizer import get_tokens
from core.similarity import final_similarity, cosine_sim
from utils.preprocessing import clean_code


# ══════════════════════════════════════════════════════════════════════════════
#  1.  DATA STRUCTURES
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class CFGNode:
    node_id:   int
    label:     str
    node_type: str = "statement"   # entry | exit | statement | condition | loop | return | call
    stmts:     List[ast.AST] = field(default_factory=list)

    def __repr__(self):
        return f"CFGNode({self.node_id}, {self.node_type}, {self.label!r})"


class CFGEdge:
    def __init__(self, src: CFGNode, dst: CFGNode, label: str = ""):
        self.src, self.dst, self.label = src, dst, label

    def __repr__(self):
        return f"CFGEdge({self.src.node_id} → {self.dst.node_id}, {self.label!r})"


class CFG:
    """Container: holds nodes + edges, can export to DOT or a summary dict."""

    def __init__(self):
        self._counter = 0
        self.nodes:  List[CFGNode] = []
        self.edges:  List[CFGEdge] = []
        self.entry:  Optional[CFGNode] = None
        self.exit:   Optional[CFGNode] = None

    # ── internals ────────────────────────────────────────────────────────────
    def _new_node(self, label: str, node_type: str = "statement") -> CFGNode:
        n = CFGNode(node_id=self._counter, label=label, node_type=node_type)
        self._counter += 1
        self.nodes.append(n)
        return n

    def _add_edge(self, src, dst, label: str = ""):
        if src is not None and dst is not None:
            self.edges.append(CFGEdge(src, dst, label))

    # ── public ───────────────────────────────────────────────────────────────
    def to_dot(self) -> str:
        """Return a Graphviz DOT string — paste at https://dreampuf.github.io/GraphvizOnline/"""
        COLOR = {
            "entry":     "lightblue",
            "exit":      "lightcoral",
            "condition": "lightyellow",
            "loop":      "lightgreen",
            "return":    "lightsalmon",
            "call":      "lavender",
            "statement": "white",
        }
        lines = [
            "digraph CFG {",
            "  rankdir=TB;",
            '  node [shape=box, style=filled, fontname="Courier New", fontsize=9];',
            '  edge [fontname="Courier New", fontsize=8];',
            "",
        ]
        for n in self.nodes:
            lbl = n.label.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
            lines.append(f'  N{n.node_id} [label="{lbl}", fillcolor="{COLOR.get(n.node_type, "white")}"];')
        lines.append("")
        for e in self.edges:
            lbl = e.label.replace('"', '\\"')
            attr = f' [label="{lbl}"]' if lbl else ""
            lines.append(f"  N{e.src.node_id} -> N{e.dst.node_id}{attr};")
        lines.append("}")
        return "\n".join(lines)

    def summary(self) -> dict:
        return {
            "num_nodes": len(self.nodes),
            "num_edges": len(self.edges),
            "nodes": [{"id": n.node_id, "label": n.label, "type": n.node_type} for n in self.nodes],
            "edges": [{"from": e.src.node_id, "to": e.dst.node_id, "label": e.label} for e in self.edges],
        }


# ══════════════════════════════════════════════════════════════════════════════
#  2.  CFG BUILDER
# ══════════════════════════════════════════════════════════════════════════════

class CFGBuilder:
    """
    Walks AST statement lists and wires CFGNodes together.

    Each _visit_* returns (entry_node, [exit_nodes]).
    _build_stmts() chains them sequentially and handles branching.
    """

    def __init__(self):
        self.cfg = CFG()

    @staticmethod
    def _label(node: ast.AST) -> str:
        try:
            t = ast.unparse(node)
            return t if len(t) <= 60 else t[:57] + "..."
        except Exception:
            return type(node).__name__

    # ── dispatcher ───────────────────────────────────────────────────────────
    def _visit_stmt(self, stmt) -> Tuple[Optional[CFGNode], List[CFGNode]]:
        if isinstance(stmt, ast.If):
            return self._visit_if(stmt)
        if isinstance(stmt, ast.For):
            return self._visit_for(stmt)
        if isinstance(stmt, ast.While):
            return self._visit_while(stmt)
        if isinstance(stmt, ast.Return):
            return self._visit_return(stmt)
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return self._visit_funcdef(stmt)
        if isinstance(stmt, ast.With):
            return self._visit_with(stmt)
        if isinstance(stmt, ast.Try):
            return self._visit_try(stmt)
        if isinstance(stmt, ast.Expr) and isinstance(getattr(stmt, "value", None), ast.Call):
            return self._visit_call(stmt)
        return self._visit_generic(stmt)

    # ── leaf visitors ─────────────────────────────────────────────────────────
    def _visit_generic(self, stmt):
        n = self.cfg._new_node(self._label(stmt), "statement")
        n.stmts.append(stmt)
        return n, [n]

    def _visit_call(self, stmt):
        n = self.cfg._new_node(self._label(stmt), "call")
        n.stmts.append(stmt)
        return n, [n]

    def _visit_return(self, stmt):
        n = self.cfg._new_node(self._label(stmt), "return")
        n.stmts.append(stmt)
        return n, []          # return has no successors in its block

    def _visit_funcdef(self, stmt):
        # Shows as a single reference node in the parent CFG.
        # build_cfg_per_function() gives you the full internal CFG.
        n = self.cfg._new_node(f"def {stmt.name}(...)", "entry")
        return n, [n]

    # ── compound visitors ─────────────────────────────────────────────────────
    def _visit_if(self, stmt):
        cond = self.cfg._new_node(f"if {self._label(stmt.test)}", "condition")
        cond.stmts.append(stmt)

        true_first, true_exits = self._build_stmts(stmt.body)
        if true_first:
            self.cfg._add_edge(cond, true_first, "True")
        else:
            true_exits = [cond]

        if stmt.orelse:
            false_first, false_exits = self._build_stmts(stmt.orelse)
            if false_first:
                self.cfg._add_edge(cond, false_first, "False")
            else:
                false_exits = [cond]
        else:
            false_exits = [cond]

        return cond, true_exits + false_exits

    def _visit_for(self, stmt):
        lbl = f"for {self._label(stmt.target)} in {self._label(stmt.iter)}"
        loop = self.cfg._new_node(lbl, "loop")
        loop.stmts.append(stmt)
        return self._wire_loop(loop, stmt.body, stmt.orelse)

    def _visit_while(self, stmt):
        loop = self.cfg._new_node(f"while {self._label(stmt.test)}", "loop")
        loop.stmts.append(stmt)
        return self._wire_loop(loop, stmt.body, stmt.orelse)

    def _wire_loop(self, loop_node, body, orelse):
        body_first, body_exits = self._build_stmts(body)
        if body_first:
            self.cfg._add_edge(loop_node, body_first, "loop body")
        for ex in body_exits:
            self.cfg._add_edge(ex, loop_node, "back")     # back-edge = the cycle

        if orelse:
            else_first, else_exits = self._build_stmts(orelse)
            if else_first:
                self.cfg._add_edge(loop_node, else_first, "else")
            return loop_node, else_exits
        return loop_node, [loop_node]

    def _visit_with(self, stmt):
        try:
            items = ", ".join(ast.unparse(i) for i in stmt.items)
        except Exception:
            items = "..."
        n = self.cfg._new_node(f"with {items}", "statement")
        n.stmts.append(stmt)
        body_first, body_exits = self._build_stmts(stmt.body)
        if body_first:
            self.cfg._add_edge(n, body_first)
        return n, body_exits or [n]

    def _visit_try(self, stmt):
        try_node = self.cfg._new_node("try", "statement")
        try_node.stmts.append(stmt)
        body_first, body_exits = self._build_stmts(stmt.body)
        if body_first:
            self.cfg._add_edge(try_node, body_first, "try")
        all_exits = list(body_exits)

        for handler in stmt.handlers:
            exc_lbl = f"except {ast.unparse(handler.type)}" if handler.type else "except"
            exc_n = self.cfg._new_node(exc_lbl, "condition")
            self.cfg._add_edge(try_node, exc_n, "exception")
            _, h_exits = self._build_stmts(handler.body, exc_n)
            all_exits.extend(h_exits)

        if stmt.orelse:
            ef, ee = self._build_stmts(stmt.orelse)
            if ef:
                self.cfg._add_edge(try_node, ef, "else")
            all_exits.extend(ee)

        if stmt.finalbody:
            ff, fe = self._build_stmts(stmt.finalbody)
            if ff:
                for ex in all_exits:
                    self.cfg._add_edge(ex, ff, "finally")
            all_exits = fe or [try_node]

        return try_node, all_exits or [try_node]

    # ── sequential chainer ────────────────────────────────────────────────────
    def _build_stmts(self, stmts, predecessor=None):
        if not stmts:
            return predecessor, ([predecessor] if predecessor else [])

        current_exits = [predecessor] if predecessor else []
        first_node = None

        for stmt in stmts:
            entry, exits = self._visit_stmt(stmt)
            if entry is None:
                continue
            if first_node is None:
                first_node = entry
            for prev in current_exits:
                self.cfg._add_edge(prev, entry)
            current_exits = exits

        return first_node, current_exits

    # ── public build ──────────────────────────────────────────────────────────
    def build(self, tree, scope_name=None) -> CFG:
        self.cfg = CFG()
        label = scope_name or "module"

        entry = self.cfg._new_node(f"ENTRY: {label}", "entry")
        self.cfg.entry = entry

        if isinstance(tree, ast.Module):
            stmts = tree.body
        elif isinstance(tree, (ast.FunctionDef, ast.AsyncFunctionDef)):
            stmts = tree.body
        else:
            stmts = list(ast.iter_child_nodes(tree))

        _, exits = self._build_stmts(stmts, entry)

        exit_node = self.cfg._new_node("EXIT", "exit")
        self.cfg.exit = exit_node
        for ex in exits:
            self.cfg._add_edge(ex, exit_node)

        return self.cfg


# ══════════════════════════════════════════════════════════════════════════════
#  3.  PUBLIC HELPER FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

def build_cfg(ast_tree, scope_name=None) -> Optional[CFG]:
    """Build one CFG for the whole file/function tree. Pass None → returns None."""
    if ast_tree is None:
        return None
    return CFGBuilder().build(ast_tree, scope_name=scope_name)


def build_cfg_per_function(ast_tree) -> Dict[str, CFG]:
    """Build a separate CFG for every top-level function. Returns {name: CFG}."""
    if ast_tree is None:
        return {}
    result = {}
    for node in ast.iter_child_nodes(ast_tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            result[node.name] = CFGBuilder().build(node, scope_name=node.name)
    return result


def export_cfg_dot(cfg: CFG, filepath: str) -> str:
    """Write CFG to a .dot file. Render with: dot -Tpng file.dot -o file.png"""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(cfg.to_dot())
    return filepath


def cfg_node_sequence(cfg: CFG) -> str:
    """BFS node-type sequence — used as a structural fingerprint for similarity."""
    if cfg.entry is None:
        return ""
    adj = {n.node_id: [] for n in cfg.nodes}
    for e in cfg.edges:
        adj[e.src.node_id].append(e.dst)
    visited, queue, seq = set(), [cfg.entry], []
    while queue:
        node = queue.pop(0)
        if node.node_id in visited:
            continue
        visited.add(node.node_id)
        seq.append(node.node_type)
        for nxt in adj.get(node.node_id, []):
            if nxt.node_id not in visited:
                queue.append(nxt)
    return " ".join(seq)


# ══════════════════════════════════════════════════════════════════════════════
#  4.  CFG SIMILARITY
# ══════════════════════════════════════════════════════════════════════════════

def _type_histogram(cfg: CFG) -> Dict[str, int]:
    return Counter(n.node_type for n in cfg.nodes)


def _histogram_sim(h1, h2) -> float:
    keys = set(h1) | set(h2)
    if not keys:
        return 1.0
    dot  = sum(h1.get(k, 0) * h2.get(k, 0) for k in keys)
    mag1 = math.sqrt(sum(v * v for v in h1.values()))
    mag2 = math.sqrt(sum(v * v for v in h2.values()))
    if mag1 == 0 or mag2 == 0:
        return 1.0 if mag1 == mag2 else 0.0
    return dot / (mag1 * mag2)


def _density_sim(cfg1, cfg2) -> float:
    r1 = len(cfg1.edges) / max(len(cfg1.nodes), 1)
    r2 = len(cfg2.edges) / max(len(cfg2.nodes), 1)
    return math.exp(-abs(r1 - r2))


def cfg_similarity_score(cfg1: Optional[CFG], cfg2: Optional[CFG]) -> float:
    """
    CFG similarity in [0, 1].
    Combines: 60% BFS sequence shape + 30% node-type histogram + 10% graph density.
    """
    if cfg1 is None or cfg2 is None:
        return 0.0
    seq_score  = cosine_sim(cfg_node_sequence(cfg1), cfg_node_sequence(cfg2), ngram_range=(1, 2))
    hist_score = _histogram_sim(_type_histogram(cfg1), _type_histogram(cfg2))
    edge_score = _density_sim(cfg1, cfg2)
    return round(0.60 * seq_score + 0.30 * hist_score + 0.10 * edge_score, 4)


# ══════════════════════════════════════════════════════════════════════════════
#  5.  CLI RUNNER
# ══════════════════════════════════════════════════════════════════════════════

def _banner(text):
    print("\n" + "─" * 66)
    print(f"  {text}")
    print("─" * 66)


def _load(path):
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        raw = f.read()
    code = clean_code(raw)
    tree, err = get_ast_tree(code)
    tokens = get_tokens(code)
    cfg = build_cfg(tree, scope_name=os.path.basename(path)) if not err else None
    fn_cfgs = build_cfg_per_function(tree) if not err else {}
    return dict(path=path, name=os.path.basename(path), code=code,
                tree=tree, err=err, tokens=tokens, cfg=cfg, fn_cfgs=fn_cfgs)


def _print_single(a):
    _banner(f"CFG Analysis  ▸  {a['name']}")
    if a["err"]:
        print(f"  ✗  Parse error: {a['err']}")
        return
    s = a["cfg"].summary()
    print(f"  Nodes : {s['num_nodes']}")
    print(f"  Edges : {s['num_edges']}")
    types = Counter(n["type"] for n in s["nodes"])
    print("  Node types:")
    for t, c in sorted(types.items()):
        print(f"    {t:<12} {c:>3}  {'█' * c}")
    if a["fn_cfgs"]:
        print("  Per-function:")
        for fn, fc in a["fn_cfgs"].items():
            fs = fc.summary()
            print(f"    def {fn}()  →  {fs['num_nodes']} nodes, {fs['num_edges']} edges")
            for n in fc.nodes:
                print(f"      [{n.node_id}] {n.node_type:<12} {n.label}")


def _compare_pair(a, b):
    ast_score = 0.0
    if not a["err"] and not b["err"]:
        ast_score = final_similarity(
            ast.dump(a["tree"]), ast.dump(b["tree"]),
            a["tokens"], b["tokens"]
        )
    cfg_score = cfg_similarity_score(a["cfg"], b["cfg"])

    def verdict(pct):
        if pct > 80: return "🔴  HIGHLY SIMILAR"
        if pct > 60: return "🟡  MODERATE"
        return "🟢  LOW SIMILARITY"

    _banner(f"{a['name']}  ↔  {b['name']}")
    if a["err"]: print(f"  ✗  {a['name']}: {a['err']}")
    if b["err"]: print(f"  ✗  {b['name']}: {b['err']}")
    if not a["err"] and not b["err"]:
        print(f"  AST + Token score  : {int(ast_score*100):>3}%  {verdict(int(ast_score*100))}")
        print(f"  CFG structure score: {int(cfg_score*100):>3}%  {verdict(int(cfg_score*100))}")


def main():
    parser = argparse.ArgumentParser(description="PlagiCheck — CFG analysis (existing pipeline untouched)")
    parser.add_argument("files", nargs="+", metavar="FILE.py")
    parser.add_argument("--dot-dir", metavar="DIR", default=None,
                        help="Save Graphviz .dot files here")
    args = parser.parse_args()

    artefacts = []
    for path in args.files:
        if not os.path.isfile(path):
            print(f"[WARN] Not found: {path}", file=sys.stderr)
            continue
        try:
            artefacts.append(_load(path))
        except Exception as e:
            print(f"[WARN] Could not load {path}: {e}", file=sys.stderr)

    if not artefacts:
        print("No valid files.", file=sys.stderr); sys.exit(1)

    for a in artefacts:
        _print_single(a)

    if len(artefacts) >= 2:
        print("\n\n" + "═" * 66)
        print("  PAIRWISE COMPARISON")
        print("═" * 66)
        for a, b in itertools.combinations(artefacts, 2):
            _compare_pair(a, b)

    if args.dot_dir:
        os.makedirs(args.dot_dir, exist_ok=True)
        _banner(f"Exporting DOT files  →  {args.dot_dir}/")
        for a in artefacts:
            if a["cfg"] is None: continue
            stem = os.path.splitext(a["name"])[0]
            p = export_cfg_dot(a["cfg"], os.path.join(args.dot_dir, f"{stem}.dot"))
            print(f"  ✔  {p}")
            for fn, fc in a["fn_cfgs"].items():
                p2 = export_cfg_dot(fc, os.path.join(args.dot_dir, f"{stem}__{fn}.dot"))
                print(f"  ✔  {p2}")
        print("\n  Render : dot -Tpng <file>.dot -o <file>.png")
        print("  Online : https://dreampuf.github.io/GraphvizOnline/")

    
    print()


if __name__ == "__main__":
    main()

# =============================================================================
#  enhancement_layer.py
#  Drop-in enhancement layer for PlagiCheck (Plagiarism-Detection-System-using-AST)
#
#  HOW TO PLUG INTO app.py
#  ────────────────────────
#  1. Copy this file into the project root (same level as app.py).
#  2. At the top of app.py, add ONE import line:
#
#       from enhancement_layer import enhance_results
#
#  3. Inside app_page(), AFTER the `components.html(report_html, ...)` call,
#     paste:
#
#       enhance_results(pairs, filenames, codes)
#
#     That's it. All buttons, downloads, and CFG images appear automatically.
#
#  INSTALL (add to requirements.txt or run once):
#       pip install reportlab networkx matplotlib
#
#  DEPENDENCIES SUMMARY:
#       reportlab   – PDF generation
#       networkx    – CFG graph building
#       matplotlib  – CFG graph rendering to PNG
#       (streamlit, scikit-learn, ast already used by the project)
# =============================================================================

from __future__ import annotations

import ast
import io
import json
import logging
import os
import re
import tempfile
import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# ── logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("enhancement_layer")


# =============================================================================
#  1. SAFE PREPROCESSING IMPROVEMENTS
#     Optional wrapper — does NOT replace core/utils/preprocessing.py
# =============================================================================

def remove_comments(code: str) -> str:
    """
    Safely remove single-line Python comments while preserving string literals.
    This is purely additive — the original clean_code() in utils/preprocessing.py
    is intentionally a no-op (the project relies on AST ignoring comments).
    Use this only when you want cleaner token extraction, not for AST parsing.
    """
    try:
        result_lines = []
        for line in code.splitlines():
            # Tokenize each line character by character to skip # outside strings
            in_single = False
            in_double = False
            clean = []
            i = 0
            while i < len(line):
                ch = line[i]
                if ch == "'" and not in_double:
                    in_single = not in_single
                elif ch == '"' and not in_single:
                    in_double = not in_double
                elif ch == "#" and not in_single and not in_double:
                    break           # rest of line is a comment
                clean.append(ch)
                i += 1
            result_lines.append("".join(clean))
        return "\n".join(result_lines)
    except Exception as exc:
        log.warning("remove_comments fell back to original: %s", exc)
        return code


def strip_extra_whitespace(code: str) -> str:
    """
    Collapse multiple blank lines to one and strip trailing spaces.
    Purely cosmetic — does not affect AST or tokens.
    """
    try:
        lines = [ln.rstrip() for ln in code.splitlines()]
        cleaned: List[str] = []
        prev_blank = False
        for ln in lines:
            is_blank = ln.strip() == ""
            if is_blank and prev_blank:
                continue          # drop consecutive blank lines
            cleaned.append(ln)
            prev_blank = is_blank
        return "\n".join(cleaned).strip()
    except Exception as exc:
        log.warning("strip_extra_whitespace fell back to original: %s", exc)
        return code


def enhanced_preprocess(code: str) -> str:
    """
    Convenience wrapper: remove comments → strip whitespace.
    Safe to call; returns original code on any failure.
    """
    try:
        code = remove_comments(code)
        code = strip_extra_whitespace(code)
        return code
    except Exception as exc:
        log.warning("enhanced_preprocess failed, returning raw code: %s", exc)
        return code


# =============================================================================
#  2. ERROR HANDLING WRAPPERS
# =============================================================================

def safe_parse(code: str, filename: str = "<unknown>") -> Tuple[Optional[ast.AST], Optional[str]]:
    """
    Wraps core.parser.get_ast_tree with graceful error handling.
    Returns (tree_or_None, error_message_or_None).
    Logs the error cleanly without crashing the caller.
    """
    try:
        from core.parser import get_ast_tree          # noqa: PLC0415
        tree, err = get_ast_tree(code)
        if err:
            log.warning("Parse error in '%s': %s", filename, err)
        return tree, err
    except ImportError:
        msg = "core.parser not found — run from project root"
        log.error(msg)
        return None, msg
    except Exception as exc:
        msg = f"Unexpected error parsing '{filename}': {exc}"
        log.error(msg)
        log.debug(traceback.format_exc())
        return None, msg


def safe_tokenize(code: str, filename: str = "<unknown>") -> List[str]:
    """
    Wraps core.tokenizer.get_tokens with graceful error handling.
    Returns an empty list on failure instead of raising.
    """
    try:
        from core.tokenizer import get_tokens          # noqa: PLC0415
        tokens = get_tokens(code)
        return tokens
    except ImportError:
        log.error("core.tokenizer not found — run from project root")
        return []
    except Exception as exc:
        log.warning("Tokenization error in '%s': %s", filename, exc)
        return []


def safe_similarity(ast_dump1: str, ast_dump2: str,
                    tokens1: List[str], tokens2: List[str]) -> float:
    """
    Wraps core.similarity.final_similarity with graceful error handling.
    Returns 0.0 on failure.
    """
    try:
        from core.similarity import final_similarity   # noqa: PLC0415
        return float(final_similarity(ast_dump1, ast_dump2, tokens1, tokens2))
    except ImportError:
        log.error("core.similarity not found — run from project root")
        return 0.0
    except Exception as exc:
        log.warning("Similarity computation failed: %s", exc)
        return 0.0


# =============================================================================
#  3. PLAGIARISM LEVEL CLASSIFICATION
# =============================================================================

def classify_score(score: float) -> Tuple[str, str, str]:
    """
    Returns (level, emoji, color_hex) for a similarity score in [0, 1].
      High   → score > 0.80
      Medium → score > 0.60
      Low    → score ≤ 0.60
    Thresholds match the ones hard-coded in app.py so UI is consistent.
    """
    if score > 0.80:
        return "High", "🔴", "#ff3d5a"
    elif score > 0.60:
        return "Medium", "🟡", "#ffc400"
    else:
        return "Low", "🟢", "#00e676"


# =============================================================================
#  4. CFG VISUALIZATION
#     Builds a Control-Flow-Graph from the AST produced by core/parser.py.
#     Does NOT touch cfg_module — it simply wraps the AST output.
# =============================================================================

def _build_cfg_from_ast(tree: ast.AST) -> Tuple[List[Tuple[str, str]], List[Tuple[str, str]]]:
    """
    Walk the AST and produce a simple, readable CFG:
      nodes → list of (node_id, label)
      edges → list of (from_id, to_id)

    Strategy: treat each top-level statement as a CFG node and connect
    them in sequence.  Branch nodes (If, For, While, Try) spawn child
    sub-graphs to show control flow.
    """
    nodes: List[Tuple[str, str]] = []
    edges: List[Tuple[str, str]] = []
    counter = [0]

    def new_id() -> str:
        counter[0] += 1
        return f"n{counter[0]}"

    def node_label(stmt: ast.stmt) -> str:
        """Short human-readable label for a statement node."""
        name = type(stmt).__name__
        try:
            if isinstance(stmt, ast.FunctionDef):
                return f"def {stmt.name}()"
            if isinstance(stmt, ast.AsyncFunctionDef):
                return f"async def {stmt.name}()"
            if isinstance(stmt, ast.ClassDef):
                return f"class {stmt.name}"
            if isinstance(stmt, ast.Return):
                return "return"
            if isinstance(stmt, ast.Assign):
                return "assign"
            if isinstance(stmt, ast.AugAssign):
                return "aug-assign"
            if isinstance(stmt, ast.AnnAssign):
                return "ann-assign"
            if isinstance(stmt, ast.Expr):
                if isinstance(stmt.value, ast.Call):
                    fn = stmt.value.func
                    if isinstance(fn, ast.Name):
                        return f"call {fn.id}()"
                    if isinstance(fn, ast.Attribute):
                        return f"call .{fn.attr}()"
                return "expr"
            if isinstance(stmt, ast.If):
                return "if (branch)"
            if isinstance(stmt, ast.For):
                return "for (loop)"
            if isinstance(stmt, ast.While):
                return "while (loop)"
            if isinstance(stmt, ast.Try):
                return "try / except"
            if isinstance(stmt, ast.With):
                return "with (ctx)"
            if isinstance(stmt, ast.Import):
                names = ", ".join(a.name for a in stmt.names[:2])
                return f"import {names}"
            if isinstance(stmt, ast.ImportFrom):
                return f"from {stmt.module} import …"
            if isinstance(stmt, ast.Raise):
                return "raise"
            if isinstance(stmt, ast.Delete):
                return "del"
            if isinstance(stmt, ast.Pass):
                return "pass"
            if isinstance(stmt, ast.Break):
                return "break"
            if isinstance(stmt, ast.Continue):
                return "continue"
            if isinstance(stmt, ast.Global):
                return "global"
            if isinstance(stmt, ast.Nonlocal):
                return "nonlocal"
        except Exception:
            pass
        return name

    def walk_body(stmts: List[ast.stmt], prev_id: Optional[str] = None) -> Optional[str]:
        """Walk a list of statements; return id of last node added."""
        last = prev_id
        for stmt in stmts:
            nid = new_id()
            label = node_label(stmt)
            nodes.append((nid, label))
            if last:
                edges.append((last, nid))
            last = nid
            # Recurse into branch bodies so they appear as sub-graphs
            if isinstance(stmt, ast.If):
                branch_end = walk_body(stmt.body, nid)
                if stmt.orelse:
                    else_end = walk_body(stmt.orelse, nid)
                    # merge point
                    merge = new_id()
                    nodes.append((merge, "merge"))
                    if branch_end:
                        edges.append((branch_end, merge))
                    if else_end:
                        edges.append((else_end, merge))
                    last = merge
            elif isinstance(stmt, (ast.For, ast.While)):
                loop_end = walk_body(stmt.body, nid)
                if loop_end and loop_end != nid:
                    edges.append((loop_end, nid))  # back-edge
            elif isinstance(stmt, ast.FunctionDef):
                walk_body(stmt.body, nid)
            elif isinstance(stmt, ast.ClassDef):
                walk_body(stmt.body, nid)
            elif isinstance(stmt, ast.Try):
                walk_body(stmt.body, nid)
                for handler in stmt.handlers:
                    walk_body(handler.body, nid)
                if stmt.finalbody:
                    walk_body(stmt.finalbody, nid)
        return last

    try:
        if hasattr(tree, "body"):
            start_id = new_id()
            nodes.append((start_id, "START"))
            last = walk_body(tree.body, start_id)
            if last and last != start_id:
                end_id = new_id()
                nodes.append((end_id, "END"))
                edges.append((last, end_id))
    except Exception as exc:
        log.warning("CFG construction error: %s", exc)

    return nodes, edges


def generate_cfg_image(tree: ast.AST, filename: str,
                        output_dir: Optional[str] = None) -> Optional[str]:
    """
    Build a CFG from *tree* (output of core.parser.get_ast_tree) and save
    it as a PNG.  Returns the PNG file path, or None on failure.

    Parameters
    ----------
    tree       : AST object returned by get_ast_tree()
    filename   : source file name — used to name the output PNG
    output_dir : where to save the PNG (defaults to system temp dir)
    """
    try:
        import networkx as nx                   # noqa: PLC0415
        import matplotlib                       # noqa: PLC0415
        matplotlib.use("Agg")                   # headless — no display needed
        import matplotlib.pyplot as plt         # noqa: PLC0415
        import matplotlib.patches as mpatches  # noqa: PLC0415
    except ImportError as exc:
        log.error("CFG visualization requires networkx and matplotlib: %s", exc)
        return None

    try:
        cfg_nodes, cfg_edges = _build_cfg_from_ast(tree)

        if not cfg_nodes:
            log.warning("No CFG nodes for '%s' — skipping visualization", filename)
            return None

        G = nx.DiGraph()
        for nid, label in cfg_nodes:
            G.add_node(nid, label=label)
        for src, dst in cfg_edges:
            G.add_edge(src, dst)

        # ── layout ────────────────────────────────────────────────────────
        # Use a layered layout when possible; fall back to spring layout
        try:
            pos = nx.drawing.nx_agraph.graphviz_layout(G, prog="dot")
        except Exception:
            try:
                pos = nx.planar_layout(G)
            except Exception:
                pos = nx.spring_layout(G, seed=42, k=2.5)

        # ── colours: START=cyan, END=green, branch=amber, rest=dark-blue ──
        label_map = {nid: lbl for nid, lbl in cfg_nodes}
        node_colors = []
        for nid in G.nodes():
            lbl = label_map.get(nid, "")
            if lbl == "START":
                node_colors.append("#00e5ff")
            elif lbl == "END":
                node_colors.append("#00e676")
            elif "branch" in lbl or "loop" in lbl or "merge" in lbl:
                node_colors.append("#ffc400")
            else:
                node_colors.append("#1a3a5c")

        n_nodes = len(G.nodes())
        fig_w = max(10, min(22, n_nodes * 1.4))
        fig_h = max(7,  min(16, n_nodes * 0.9))

        fig, ax = plt.subplots(figsize=(fig_w, fig_h))
        fig.patch.set_facecolor("#080a0f")
        ax.set_facecolor("#0e1218")

        nx.draw_networkx_edges(
            G, pos, ax=ax,
            edge_color="#263040",
            arrows=True,
            arrowstyle="-|>",
            arrowsize=18,
            width=1.4,
            connectionstyle="arc3,rad=0.08",
        )
        nx.draw_networkx_nodes(
            G, pos, ax=ax,
            node_color=node_colors,
            node_size=1800,
            alpha=0.92,
        )
        nx.draw_networkx_labels(
            G, pos, ax=ax,
            labels=label_map,
            font_size=7,
            font_color="#c8d6e8",
            font_family="monospace",
        )

        # legend
        legend_patches = [
            mpatches.Patch(color="#00e5ff", label="START"),
            mpatches.Patch(color="#00e676", label="END"),
            mpatches.Patch(color="#ffc400", label="Branch / Loop"),
            mpatches.Patch(color="#1a3a5c", label="Statement"),
        ]
        ax.legend(handles=legend_patches, loc="upper right",
                  facecolor="#121820", edgecolor="#263040",
                  labelcolor="#c8d6e8", fontsize=7)

        clean_name = re.sub(r"[^\w\-.]", "_", os.path.basename(filename))
        title = f"Control Flow Graph — {clean_name}"
        ax.set_title(title, color="#c8d6e8", fontsize=9,
                     fontfamily="monospace", pad=12)
        ax.axis("off")
        plt.tight_layout()

        out_dir = output_dir or tempfile.gettempdir()
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"cfg_{clean_name}.png")
        plt.savefig(out_path, dpi=130, bbox_inches="tight",
                    facecolor=fig.get_facecolor())
        plt.close(fig)
        log.info("CFG image saved: %s", out_path)
        return out_path

    except Exception as exc:
        log.error("CFG image generation failed for '%s': %s", filename, exc)
        log.debug(traceback.format_exc())
        return None


# =============================================================================
#  5. REPORT GENERATION
# =============================================================================

# ── 5a. JSON report ───────────────────────────────────────────────────────────

def generate_json_report(pairs: List[Dict[str, Any]],
                          filenames: List[str]) -> bytes:
    """
    Build a JSON report from pair-wise similarity results.

    Parameters
    ----------
    pairs     : list of dicts with keys: file1, file2, score
    filenames : all filenames analysed

    Returns bytes (UTF-8 encoded JSON).
    """
    level_map = {r["file1"] + r["file2"]: classify_score(r["score"])[0]
                 for r in pairs}

    report = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "tool": "PlagiCheck — AST + Token Hybrid Engine",
        "files_analysed": filenames,
        "total_pairs": len(pairs),
        "results": [
            {
                "file_1": r["file1"],
                "file_2": r["file2"],
                "similarity_score": round(r["score"], 4),
                "similarity_pct": f"{int(r['score'] * 100)}%",
                "plagiarism_level": classify_score(r["score"])[0],
            }
            for r in pairs
        ],
        "summary": {
            "high_risk_pairs":   sum(1 for r in pairs if r["score"] > 0.80),
            "medium_risk_pairs": sum(1 for r in pairs if 0.60 < r["score"] <= 0.80),
            "low_risk_pairs":    sum(1 for r in pairs if r["score"] <= 0.60),
        },
    }
    return json.dumps(report, indent=2, ensure_ascii=False).encode("utf-8")


# ── 5b. PDF report ────────────────────────────────────────────────────────────

def generate_pdf_report(pairs: List[Dict[str, Any]],
                         filenames: List[str]) -> Optional[bytes]:
    """
    Build a clean, readable PDF report using ReportLab.
    Returns PDF bytes, or None if reportlab is not installed.

    Parameters
    ----------
    pairs     : list of dicts with keys: file1, file2, score
    filenames : all filenames analysed
    """
    try:
        from reportlab.lib import colors                      # noqa: PLC0415
        from reportlab.lib.pagesizes import A4               # noqa: PLC0415
        from reportlab.lib.styles import getSampleStyleSheet  # noqa: PLC0415
        from reportlab.lib.units import cm                   # noqa: PLC0415
        from reportlab.platypus import (                     # noqa: PLC0415
            HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table,
            TableStyle,
        )
    except ImportError:
        log.error("reportlab not installed — PDF report unavailable. "
                  "Install with: pip install reportlab")
        return None

    try:
        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf,
            pagesize=A4,
            rightMargin=2 * cm, leftMargin=2 * cm,
            topMargin=2 * cm,   bottomMargin=2 * cm,
        )
        styles = getSampleStyleSheet()
        story = []

        # ── title block ───────────────────────────────────────────────
        title_style = styles["Title"]
        title_style.textColor = colors.HexColor("#00b8cc")
        story.append(Paragraph("PlagiCheck — Plagiarism Analysis Report", title_style))
        story.append(Spacer(1, 0.3 * cm))

        body = styles["BodyText"]
        body.fontSize = 9

        stamp = datetime.utcnow().strftime("%d %b %Y %H:%M UTC")
        story.append(Paragraph(f"Generated: {stamp}", body))
        story.append(Paragraph(f"Files analysed: {len(filenames)}", body))
        story.append(Paragraph(f"Total pairs compared: {len(pairs)}", body))
        story.append(Spacer(1, 0.4 * cm))
        story.append(HRFlowable(width="100%", thickness=1,
                                 color=colors.HexColor("#cccccc")))
        story.append(Spacer(1, 0.4 * cm))

        # ── files list ────────────────────────────────────────────────
        h2 = styles["Heading2"]
        h2.textColor = colors.HexColor("#333333")
        story.append(Paragraph("Analysed Files", h2))
        for i, fname in enumerate(filenames, 1):
            story.append(Paragraph(f"{i}. {fname}", body))
        story.append(Spacer(1, 0.5 * cm))

        # ── summary box ───────────────────────────────────────────────
        story.append(Paragraph("Summary", h2))
        high   = sum(1 for r in pairs if r["score"] > 0.80)
        medium = sum(1 for r in pairs if 0.60 < r["score"] <= 0.80)
        low    = sum(1 for r in pairs if r["score"] <= 0.60)

        summary_data = [
            ["Risk Level", "Pairs", "Threshold"],
            ["🔴  High",   str(high),   "> 80%"],
            ["🟡  Medium", str(medium),  "61 – 80%"],
            ["🟢  Low",    str(low),     "≤ 60%"],
        ]
        summary_tbl = Table(summary_data, colWidths=[5 * cm, 3 * cm, 5 * cm])
        summary_tbl.setStyle(TableStyle([
            ("BACKGROUND",   (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
            ("TEXTCOLOR",    (0, 0), (-1, 0), colors.white),
            ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",     (0, 0), (-1, -1), 9),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [colors.HexColor("#f9f9f9"), colors.HexColor("#ffffff")]),
            ("GRID",         (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
            ("ALIGN",        (1, 0), (1, -1), "CENTER"),
            ("LEFTPADDING",  (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING",   (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
        ]))
        story.append(summary_tbl)
        story.append(Spacer(1, 0.6 * cm))

        # ── detailed results table ────────────────────────────────────
        story.append(Paragraph("Pair-wise Results", h2))

        col_headers = ["File 1", "File 2", "Score", "Level"]
        table_data  = [col_headers]
        row_styles  = []

        COLORS = {
            "High":   colors.HexColor("#ffe0e5"),
            "Medium": colors.HexColor("#fff8e0"),
            "Low":    colors.HexColor("#e0fff0"),
        }
        BADGE_COLORS = {
            "High":   colors.HexColor("#ff3d5a"),
            "Medium": colors.HexColor("#ffc400"),
            "Low":    colors.HexColor("#00c853"),
        }

        for row_idx, r in enumerate(pairs, start=1):
            level, emoji, _ = classify_score(r["score"])
            pct = f"{int(r['score'] * 100)}%"
            table_data.append([
                r["file1"], r["file2"], pct, f"{emoji} {level}",
            ])
            row_styles.append(
                ("BACKGROUND", (0, row_idx), (-1, row_idx), COLORS[level])
            )
            row_styles.append(
                ("TEXTCOLOR", (3, row_idx), (3, row_idx), BADGE_COLORS[level])
            )

        col_w = [6 * cm, 6 * cm, 2 * cm, 3 * cm]
        result_tbl = Table(table_data, colWidths=col_w, repeatRows=1)
        base_style = [
            ("BACKGROUND",   (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
            ("TEXTCOLOR",    (0, 0), (-1, 0), colors.white),
            ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",     (0, 0), (-1, -1), 8),
            ("GRID",         (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
            ("ALIGN",        (2, 0), (3, -1), "CENTER"),
            ("FONTNAME",     (2, 1), (3, -1), "Helvetica-Bold"),
            ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING",  (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING",   (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
            ("WORDWRAP",     (0, 0), (-1, -1), True),
        ]
        result_tbl.setStyle(TableStyle(base_style + row_styles))
        story.append(result_tbl)
        story.append(Spacer(1, 0.6 * cm))

        # ── footer ────────────────────────────────────────────────────
        story.append(HRFlowable(width="100%", thickness=0.5,
                                 color=colors.HexColor("#cccccc")))
        story.append(Spacer(1, 0.2 * cm))
        small = styles["Normal"]
        small.fontSize = 7
        small.textColor = colors.HexColor("#888888")
        story.append(Paragraph(
            "PlagiCheck • AST + Token Hybrid Engine • "
            "Scores: High > 80%  |  Medium 61–80%  |  Low ≤ 60%",
            small,
        ))

        doc.build(story)
        pdf_bytes = buf.getvalue()
        log.info("PDF report generated (%d bytes)", len(pdf_bytes))
        return pdf_bytes

    except Exception as exc:
        log.error("PDF generation failed: %s", exc)
        log.debug(traceback.format_exc())
        return None


# =============================================================================
#  6. run_full_analysis  ←  main integration entry point
# =============================================================================

def run_full_analysis(
    file_paths: List[str],
    output_dir: Optional[str] = None,
    use_enhanced_preprocess: bool = False,
) -> Dict[str, Any]:
    """
    Run the full plagiarism analysis pipeline on a list of .py files.

    Parameters
    ----------
    file_paths              : list of absolute or relative paths to .py files
    output_dir              : where to write reports + CFG images (temp if None)
    use_enhanced_preprocess : if True, apply remove_comments + strip_whitespace
                              before analysis (does NOT affect existing logic)

    Returns
    -------
    dict with keys:
        filenames   : list of base file names
        pairs       : list of result dicts (file1, file2, score, level)
        json_path   : path to the saved JSON report
        pdf_path    : path to the saved PDF report (None if reportlab missing)
        cfg_images  : dict mapping filename → PNG path (None if failed)
        errors      : list of error strings encountered
    """
    out_dir = output_dir or tempfile.mkdtemp(prefix="plagicheck_")
    os.makedirs(out_dir, exist_ok=True)

    filenames: List[str]         = []
    codes:     List[str]         = []
    trees:     List[Optional[ast.AST]] = []
    tokens_list: List[List[str]] = []
    errors:    List[str]         = []

    # ── Step 1: load and parse files ─────────────────────────────────────
    for fp in file_paths:
        fname = os.path.basename(fp)
        filenames.append(fname)
        try:
            with open(fp, "r", encoding="utf-8", errors="ignore") as fh:
                raw = fh.read()
        except Exception as exc:
            msg = f"Cannot read '{fp}': {exc}"
            log.error(msg)
            errors.append(msg)
            codes.append("")
            trees.append(None)
            tokens_list.append([])
            continue

        code = enhanced_preprocess(raw) if use_enhanced_preprocess else raw.strip()
        codes.append(code)

        tree, err = safe_parse(code, fname)
        if err:
            errors.append(f"Parse error in '{fname}': {err}")
        trees.append(tree)
        tokens_list.append(safe_tokenize(code, fname))

    # ── Step 2: pairwise similarity ───────────────────────────────────────
    pairs: List[Dict[str, Any]] = []
    for i in range(len(codes)):
        for j in range(i + 1, len(codes)):
            score = 0.0
            if trees[i] and trees[j]:
                score = safe_similarity(
                    ast.dump(trees[i]),
                    ast.dump(trees[j]),
                    tokens_list[i],
                    tokens_list[j],
                )
            level, emoji, _ = classify_score(score)
            pairs.append({
                "file1": filenames[i],
                "file2": filenames[j],
                "score": score,
                "level": level,
                "emoji": emoji,
            })

    pairs.sort(key=lambda x: x["score"], reverse=True)

    # ── Step 3: generate CFG images ───────────────────────────────────────
    cfg_images: Dict[str, Optional[str]] = {}
    for fname, tree in zip(filenames, trees):
        if tree is not None:
            png = generate_cfg_image(tree, fname, output_dir=out_dir)
            cfg_images[fname] = png
        else:
            cfg_images[fname] = None

    # ── Step 4: save JSON report ──────────────────────────────────────────
    json_bytes = generate_json_report(pairs, filenames)
    json_path  = os.path.join(out_dir, "plagicheck_report.json")
    with open(json_path, "wb") as fh:
        fh.write(json_bytes)
    log.info("JSON report saved: %s", json_path)

    # ── Step 5: save PDF report ───────────────────────────────────────────
    pdf_path: Optional[str] = None
    pdf_bytes = generate_pdf_report(pairs, filenames)
    if pdf_bytes:
        pdf_path = os.path.join(out_dir, "plagicheck_report.pdf")
        with open(pdf_path, "wb") as fh:
            fh.write(pdf_bytes)
        log.info("PDF report saved: %s", pdf_path)

    return {
        "filenames":  filenames,
        "pairs":      pairs,
        "json_path":  json_path,
        "pdf_path":   pdf_path,
        "cfg_images": cfg_images,
        "errors":     errors,
        "output_dir": out_dir,
    }


# =============================================================================
#  7. STREAMLIT HOOK  — import into app.py with ONE line
#
#     from enhancement_layer import enhance_results
#
#  Then call inside app_page() after the components.html() block:
#
#     enhance_results(pairs, filenames, codes)
#
#  `pairs` is the list of tuples app.py already builds:
#     (i, j, score, err1, err2, tree1, tree2, tokens1, tokens2)
# =============================================================================

def enhance_results(
    raw_pairs: List[Tuple],    # app.py's existing `pairs` list of 9-tuples
    filenames: List[str],
    codes: List[str],
    show_cfg: bool = True,
) -> None:
    """
    Streamlit hook — call this at the end of app_page() to add:
      • JSON download button
      • PDF download button
      • CFG images (one per file) in an expander
      • Error log expander (if any parsing errors occurred)

    Parameters
    ----------
    raw_pairs : the `pairs` list from app.py
                each item is (i, j, score, err1, err2, tree1, tree2, tok1, tok2)
    filenames : list of uploaded file names (app.py's `filenames`)
    codes     : list of source code strings  (app.py's `codes`)
    show_cfg  : set False to skip CFG generation (faster for large files)
    """
    try:
        import streamlit as st                             # noqa: PLC0415
    except ImportError:
        log.error("Streamlit not available — enhance_results() must run inside a Streamlit app")
        return

    # ── normalise pair format ─────────────────────────────────────────────
    pair_dicts: List[Dict[str, Any]] = []
    errors: List[str] = []
    trees: Dict[str, Optional[ast.AST]] = {}

    for item in raw_pairs:
        i, j, score, err1, err2, tree1, tree2, tok1, tok2 = item
        level, emoji, _ = classify_score(score)
        pair_dicts.append({
            "file1": filenames[i],
            "file2": filenames[j],
            "score": score,
            "level": level,
            "emoji": emoji,
        })
        if err1:
            errors.append(f"'{filenames[i]}': {err1}")
        if err2:
            errors.append(f"'{filenames[j]}': {err2}")
        # collect trees by filename
        if tree1 is not None:
            trees[filenames[i]] = tree1
        if tree2 is not None:
            trees[filenames[j]] = tree2

    pair_dicts.sort(key=lambda x: x["score"], reverse=True)

    # ── section header ────────────────────────────────────────────────────
    st.markdown(
        '<hr style="border:none;border-top:1px solid #1a2230;margin:2rem 0;">',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="sec-label">03 &nbsp; Export &amp; Visualizations</div>',
        unsafe_allow_html=True,
    )

    col_json, col_pdf, col_spacer = st.columns([1, 1, 3])

    # ── JSON download ─────────────────────────────────────────────────────
    with col_json:
        try:
            json_bytes = generate_json_report(pair_dicts, filenames)
            st.download_button(
                label="⬇ Download JSON",
                data=json_bytes,
                file_name="plagicheck_report.json",
                mime="application/json",
                use_container_width=True,
            )
        except Exception as exc:
            st.warning(f"JSON generation failed: {exc}")

    # ── PDF download ──────────────────────────────────────────────────────
    with col_pdf:
        try:
            pdf_bytes = generate_pdf_report(pair_dicts, filenames)
            if pdf_bytes:
                st.download_button(
                    label="⬇ Download PDF",
                    data=pdf_bytes,
                    file_name="plagicheck_report.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                )
            else:
                st.info("Install `reportlab` for PDF export.")
        except Exception as exc:
            st.warning(f"PDF generation failed: {exc}")

    # ── CFG images ────────────────────────────────────────────────────────
    if show_cfg and trees:
        with st.expander("🕸  Control Flow Graphs", expanded=False):
            st.caption(
                "CFGs are built from the normalised AST produced by the parser. "
                "Cyan = START, Green = END, Amber = branch/loop nodes."
            )
            cfg_cols = st.columns(min(len(trees), 2))
            for idx, (fname, tree) in enumerate(trees.items()):
                if tree is None:
                    continue
                with cfg_cols[idx % len(cfg_cols)]:
                    st.markdown(
                        f'<div style="font-family:\'Space Mono\',monospace;'
                        f'font-size:0.65rem;color:#4a6080;margin-bottom:0.4rem;">'
                        f'{fname}</div>',
                        unsafe_allow_html=True,
                    )
                    png_path = generate_cfg_image(tree, fname)
                    if png_path and os.path.exists(png_path):
                        with open(png_path, "rb") as img_f:
                            img_bytes = img_f.read()
                        st.image(img_bytes, use_container_width=True)
                        st.download_button(
                            label=f"⬇ CFG — {fname}",
                            data=img_bytes,
                            file_name=f"cfg_{fname}.png",
                            mime="image/png",
                            key=f"cfg_dl_{fname}_{idx}",
                        )
                    else:
                        st.warning(
                            f"CFG could not be rendered for {fname}. "
                            "Check that networkx and matplotlib are installed."
                        )

    # ── error log ─────────────────────────────────────────────────────────
    if errors:
        with st.expander(f"⚠ Parse / Analysis Errors ({len(errors)})", expanded=False):
            for err in errors:
                st.code(err, language=None)


# =============================================================================
#  CLI ENTRY POINT  — run standalone for quick testing
#  Usage:  python enhancement_layer.py file1.py file2.py file3.py
# =============================================================================

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python enhancement_layer.py <file1.py> <file2.py> [file3.py ...]")
        sys.exit(1)

    paths = sys.argv[1:]
    missing = [p for p in paths if not os.path.exists(p)]
    if missing:
        print(f"[ERROR] Files not found: {missing}")
        sys.exit(1)

    print(f"\n🔍  PlagiCheck Enhancement Layer — analysing {len(paths)} file(s)…\n")
    result = run_full_analysis(paths, use_enhanced_preprocess=True)

    print("── Results ──────────────────────────────────────")
    for pair in result["pairs"]:
        bar = "█" * int(pair["score"] * 20)
        print(
            f"  {pair['emoji']} {pair['file1']:20s} vs {pair['file2']:20s}"
            f"  {int(pair['score']*100):3d}%  [{bar:<20}]  {pair['level']}"
        )

    print(f"\n── Output saved to: {result['output_dir']}")
    print(f"   JSON report : {result['json_path']}")
    if result["pdf_path"]:
        print(f"   PDF report  : {result['pdf_path']}")
    else:
        print("   PDF report  : (install reportlab to enable)")
    print("   CFG images  :")
    for fname, png in result["cfg_images"].items():
        status = png if png else "FAILED"
        print(f"     {fname} → {status}")

    if result["errors"]:
        print("\n── Errors ───────────────────────────────────────")
        for e in result["errors"]:
            print(f"  ⚠  {e}")

    print("\n✓ Done.\n")

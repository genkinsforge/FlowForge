"""
Command-line runner: converts a Draw.io file to a Markdown file containing Mermaid code.

Usage:
    python -m flowforge diagram            # reads diagram.drawio, writes diagram.md
    python -m flowforge diagram.drawio -o out.md --direction LR
"""

import argparse
import logging
import os
import sys
import xml.etree.ElementTree as ET

from .flowforge import FlowForgeConverter


def resolve_input_path(path):
    """Append the .drawio extension when the given path has no extension."""
    if not os.path.splitext(path)[1]:
        path += ".drawio"
    return path


def get_page_names(xml_content, page_count):
    """
    Read page names from the <diagram name="..."> tags of a Draw.io file.

    Falls back to "Page N" names when the names cannot be read or do not
    line up with the pages found by the converter.
    """
    names = []
    try:
        root = ET.fromstring(xml_content)
        names = [d.get("name") or "" for d in root.iter("diagram")]
    except ET.ParseError:
        pass
    if len(names) != page_count:
        names = [""] * page_count
    return [name or f"Page {i + 1}" for i, name in enumerate(names)]


def build_markdown(title, sections):
    """
    Build the Markdown document.

    :param title: Document title (the input file's base name).
    :param sections: List of (page_name, mermaid_code) tuples. The page name
                     heading is omitted when there is only one page.
    """
    lines = [f"# {title}", ""]
    for page_name, mermaid_code in sections:
        if len(sections) > 1:
            lines += [f"## {page_name}", ""]
        lines += ["```mermaid", mermaid_code, "```", ""]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="flowforge",
        description="Convert a Draw.io diagram to a Markdown file containing Mermaid code."
    )
    parser.add_argument("input_file",
                        help="Path to the Draw.io file (.drawio is assumed if no extension is given)")
    parser.add_argument("-o", "--output",
                        help="Output .md path (default: input file name with a .md extension)")
    parser.add_argument("--index", type=int,
                        help="Convert only this diagram page index (default: all pages)")
    parser.add_argument("--direction", default="TD",
                        help="Mermaid flow direction, e.g. TD or LR (default: TD)")
    parser.add_argument("--drawio-ids", dest="readable_ids", action="store_false",
                        help="Use Draw.io cell IDs as node IDs instead of IDs made from labels")
    parser.add_argument("--strict", action="store_true",
                        help="Stop on the first conversion error")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Show detailed conversion logging")
    args = parser.parse_args(argv)

    input_path = resolve_input_path(args.input_file)
    if not os.path.isfile(input_path):
        print(f"Error: input file not found: {input_path}", file=sys.stderr)
        return 1
    output_path = args.output or os.path.splitext(input_path)[0] + ".md"

    log_level = logging.DEBUG if args.verbose else logging.WARNING
    converter = FlowForgeConverter(log_level=log_level, strict_mode=args.strict)

    try:
        xml_content = converter.load_file(input_path)
        page_indices = converter.list_diagram_pages(xml_content)
        if not page_indices:
            print(f"Error: no diagram pages found in {input_path}", file=sys.stderr)
            return 1
        page_names = get_page_names(xml_content, len(page_indices))

        if args.index is not None:
            if args.index not in page_indices:
                print(f"Error: page index {args.index} out of range "
                      f"(0 to {len(page_indices) - 1})", file=sys.stderr)
                return 1
            page_indices = [args.index]

        sections = []
        for index in page_indices:
            mermaid_code = converter.convert(xml_content, diagram_index=index,
                                             direction=args.direction,
                                             readable_ids=args.readable_ids)
            if not mermaid_code:
                print(f"Warning: page {index} ({page_names[index]}) produced no output",
                      file=sys.stderr)
                continue
            sections.append((page_names[index], mermaid_code))
    except Exception as e:
        print(f"Error: conversion failed: {e}", file=sys.stderr)
        return 1

    if not sections:
        print("Error: nothing was converted", file=sys.stderr)
        return 1

    title = os.path.splitext(os.path.basename(input_path))[0]
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(build_markdown(title, sections))
    print(f"Wrote {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

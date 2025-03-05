#!/usr/bin/env python
import argparse
import logging
from flowforge import FlowForgeConverter

def main():
    parser = argparse.ArgumentParser(
        description="Convert a Draw.io diagram to a Mermaid diagram using FlowForge"
    )
    parser.add_argument("input_file", help="Path to the Draw.io (.drawio) file")
    parser.add_argument(
        "--index",
        type=int,
        default=0,
        help="Diagram page index to convert (default: 0)"
    )
    parser.add_argument(
        "--direction",
        default="LR",
        help="Mermaid flow direction (e.g., LR for left-to-right, TD for top-down; default: LR)"
    )
    parser.add_argument(
        "--diagram-type",
        default="flowchart",
        help="Type of Mermaid diagram to generate (default: flowchart)"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Enable strict mode (conversion errors will raise exceptions)"
    )
    args = parser.parse_args()

    # Initialize FlowForgeConverter with DEBUG logging; use strict mode if specified
    converter = FlowForgeConverter(log_level=logging.DEBUG, strict_mode=args.strict)
    
    try:
        # Load the Draw.io file
        xml_content = converter.load_file(args.input_file)
        # List available diagram pages (for multi-page diagrams)
        pages = converter.list_diagram_pages(xml_content)
        print("Available diagram pages:", pages)
        
        # Convert the specified diagram page to Mermaid code
        mermaid_code = converter.convert(
            xml_content,
            diagram_index=args.index,
            direction=args.direction,
            diagram_type=args.diagram_type
        )
        
        print("=== Generated Mermaid Diagram ===")
        print(mermaid_code)
    except Exception as e:
        print(f"An error occurred during conversion: {e}")

if __name__ == "__main__":
    main()


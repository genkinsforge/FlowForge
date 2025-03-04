"""
FlowForge: Draw.io to Mermaid Converter Framework
===================================================

FlowForge is a robust, extensible Python framework for converting Draw.io (Diagram.net) diagrams
(in XML format) to Mermaid diagrams. The framework supports multiple diagram pages, enhanced style parsing,
recursive group/subgraph handling, and extensive logging with configurable error correction modes.

Usage Example:
--------------
    from flowforge import FlowForgeConverter

    # Create a converter with DEBUG logging and relaxed error handling.
    converter = FlowForgeConverter(log_level=logging.DEBUG, strict_mode=False)
    
    # Load a Draw.io file
    xml_content = converter.load_file("example.drawio")
    
    # List available diagram pages (if multiple)
    pages = converter.list_diagram_pages(xml_content)
    print("Found diagram pages:", pages)
    
    # Convert a specific diagram page (index 0 by default) to Mermaid code (flowchart).
    mermaid_code = converter.convert(xml_content, diagram_index=0, direction="LR", diagram_type="flowchart")
    print(mermaid_code)

Future extensions may add additional features and diagram types.
"""

import xml.etree.ElementTree as ET
import base64
import zlib
import re
import logging


# --- Custom Exception Classes ---
class DiagramDecompressionError(Exception):
    """Raised when the diagram data cannot be decompressed properly."""
    pass


class DiagramParsingError(Exception):
    """Raised when there is an error parsing the XML diagram."""
    pass


# --- Helper Functions ---
def parse_style(style_str):
    """
    Parse a Draw.io style string into a dictionary.
    
    The style string is a semicolon-separated list of key[=value] pairs.
    For example: "shape=ellipse;whiteSpace=wrap;html=1" 
    becomes: {"shape": "ellipse", "whiteSpace": "wrap", "html": "1"}
    
    :param style_str: The style string from a Draw.io cell.
    :return: Dictionary with style keys and values.
    """
    style_dict = {}
    if style_str:
        for token in style_str.split(';'):
            if '=' in token:
                key, value = token.split('=', 1)
                style_dict[key] = value
            else:
                # For tokens that are flags without explicit values.
                if token:
                    style_dict[token] = True
    return style_dict


# --- Main Converter Class ---
class FlowForgeConverter:
    """
    FlowForgeConverter converts Draw.io/Diagram.net diagrams to Mermaid diagrams.

    This class encapsulates the process of:
        1. Loading and (if necessary) decompressing the XML data.
        2. Parsing the XML and building an internal representation of nodes, edges, and groups.
        3. Converting the internal representation to Mermaid syntax.
    
    The converter supports multiple diagram pages in a single Draw.io file.
    Logging is integrated to provide multi-level traceability.

    Parameters:
        log_level (int): Logging level (DEBUG, INFO, WARNING, ERROR).
        strict_mode (bool): If True, errors will raise exceptions; otherwise, errors are logged and skipped.
    """

    def __init__(self, log_level=logging.INFO, strict_mode=True):
        # Set up logger
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(log_level)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

        self.strict_mode = strict_mode
        # Internal dictionaries for nodes and groups (populated during conversion)
        self.node_map = {}
        self.diagram = {"nodes": [], "edges": [], "groups": {}}
        # List of diagram pages (each page is the decompressed XML string for a <diagram> tag)
        self.diagram_pages = []

    # --- File and Data Loading Methods ---
    def load_file(self, file_path):
        """
        Loads the content of a file into a string.

        :param file_path: Path to the Draw.io file.
        :return: The file content as a string.
        :raises Exception: If file cannot be read.
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = f.read()
            self.logger.info(f"File loaded successfully: {file_path}")
            return data
        except Exception as e:
            self.logger.error(f"Error loading file '{file_path}': {str(e)}")
            raise

    # --- Decompression and Multi-Page Extraction ---
    def _decompress_data(self, xml_data):
        """
        Checks if the XML data is compressed. If the <mxGraphModel> tag is not found,
        it assumes the content inside <diagram> is compressed (base64 + deflate) and
        decompresses it. If multiple <diagram> tags are found, they are stored in self.diagram_pages.

        :param xml_data: The raw XML content.
        :return: None. Populates self.diagram_pages with decompressed XML strings.
        :raises DiagramDecompressionError: If decompression fails.
        """
        # Find all <diagram> tags
        diagrams = re.findall(r"<diagram[^>]*>(.*?)</diagram>", xml_data, re.DOTALL)
        if diagrams:
            self.logger.debug(f"Found {len(diagrams)} <diagram> tag(s). Attempting decompression.")
            for d in diagrams:
                d = d.strip()
                try:
                    decoded = base64.b64decode(d)
                    # -15 indicates raw DEFLATE stream (no header)
                    decompressed = zlib.decompress(decoded, -15).decode('utf-8')
                    # Check for the presence of <mxGraphModel> in decompressed string
                    if "<mxGraphModel" in decompressed:
                        self.diagram_pages.append(decompressed)
                        self.logger.info("Decompressed a diagram page successfully.")
                    else:
                        self.logger.warning("Decompressed data does not contain <mxGraphModel>; skipping page.")
                        if self.strict_mode:
                            raise DiagramDecompressionError("Invalid decompressed diagram content.")
                except Exception as e:
                    self.logger.error("Failed to decompress a diagram page: " + str(e))
                    if self.strict_mode:
                        raise DiagramDecompressionError(str(e))
        else:
            # If no <diagram> tags are found, assume the file is already uncompressed.
            self.logger.debug("No <diagram> tag found; assuming uncompressed XML.")
            if "<mxGraphModel" in xml_data:
                self.diagram_pages.append(xml_data)
            else:
                msg = "Input data does not contain valid Draw.io XML."
                self.logger.error(msg)
                if self.strict_mode:
                    raise DiagramDecompressionError(msg)

    def list_diagram_pages(self, xml_data):
        """
        Parses the raw file content and returns a list of diagram page indices.

        :param xml_data: The raw file content.
        :return: List of indices representing available diagram pages.
        """
        # Clear any previous pages
        self.diagram_pages = []
        self._decompress_data(xml_data)
        page_indices = list(range(len(self.diagram_pages)))
        self.logger.info(f"Diagram pages available: {page_indices}")
        return page_indices

    # --- XML Parsing and Internal Representation Building ---
    def _parse_xml(self, xml_data):
        """
        Parses an XML string into an ElementTree root.

        :param xml_data: The uncompressed XML string.
        :return: ElementTree root element.
        :raises DiagramParsingError: If XML parsing fails.
        """
        try:
            root = ET.fromstring(xml_data)
            self.logger.info("XML parsing completed successfully.")
            return root
        except ET.ParseError as e:
            self.logger.error("Error parsing XML: " + str(e))
            if self.strict_mode:
                raise DiagramParsingError(str(e))
            return None

    def _build_diagram_from_root(self, root):
        """
        Processes the XML tree starting from the <mxGraphModel> root to build the internal
        representation of nodes, edges, and groups.

        :param root: ElementTree root element of a diagram page.
        :return: A dictionary representing the diagram.
        """
        # Reset internal state
        self.node_map = {}
        self.diagram = {"nodes": [], "edges": [], "groups": {}}

        diagram_root = root.find("root")
        if diagram_root is None:
            msg = "No <root> element found in the XML."
            self.logger.error(msg)
            if self.strict_mode:
                raise DiagramParsingError(msg)
            return self.diagram

        for cell in diagram_root.findall("mxCell"):
            cell_id = cell.get("id")
            if cell_id in ("0", "1"):
                continue

            # Process vertices (nodes)
            if cell.get("vertex") == "1":
                label = cell.get("value") or ""
                style = cell.get("style") or ""
                geometry = cell.find("mxGeometry")
                node = {
                    "id": cell_id,
                    "label": label,
                    "style": style,
                    "style_dict": parse_style(style),
                    "geometry": geometry.attrib if geometry is not None else {},
                    "parent": cell.get("parent")
                }
                self.diagram["nodes"].append(node)
                self.node_map[cell_id] = node

            # Process edges (connectors)
            elif cell.get("edge") == "1":
                edge = {
                    "id": cell_id,
                    "source": cell.get("source"),
                    "target": cell.get("target"),
                    "label": cell.get("value") or "",
                    "style": cell.get("style") or "",
                    "style_dict": parse_style(cell.get("style") or "")
                }
                self.diagram["edges"].append(edge)
            else:
                self.logger.debug(f"Skipping cell id {cell_id}: not a vertex or edge.")

        self.logger.info("Built diagram: %d nodes, %d edges.",
                         len(self.diagram["nodes"]), len(self.diagram["edges"]))

        # Identify groups (e.g., swimlanes or container nodes) and support nested groups.
        for node in self.diagram["nodes"]:
            parent = node.get("parent")
            if parent and parent in self.node_map:
                # Mark node as child of a group if parent's style indicates grouping.
                parent_style = self.node_map[parent].get("style", "")
                if "group" in parent_style or "swimlane" in parent_style:
                    if parent not in self.diagram["groups"]:
                        self.diagram["groups"][parent] = {
                            "label": self.node_map[parent].get("label") or f"Group_{parent}",
                            "children": []
                        }
                    self.diagram["groups"][parent]["children"].append(node)
        return self.diagram

    # --- Node and Edge Formatting ---
    def _format_node(self, node):
        """
        Converts a single node from the internal representation to its Mermaid node definition.
        It uses the parsed style dictionary to choose the correct shape.

        :param node: Dictionary representing a node.
        :return: Mermaid node definition string.
        """
        label = node["label"].strip() if node["label"] else f"Node_{node['id']}"
        style = node["style_dict"]
        # Ensure the node ID is a valid Mermaid identifier (prefix with letter)
        node_id = "N" + node["id"]

        # Determine shape based on style properties.
        shape = style.get("shape", "").lower()
        if shape == "rhombus":
            # Decision diamond
            node_def = f'{node_id}{{"{label}"}}'
        elif shape == "ellipse" or "ellipse" in style:
            node_def = f'{node_id}(( "{label}" ))'
        elif style.get("rounded") == "1" or shape == "stadium":
            node_def = f'{node_id}("{label}")'
        else:
            # Default rectangle
            node_def = f'{node_id}["{label}"]'
        return node_def

    def _format_edge(self, edge):
        """
        Converts a single edge into Mermaid connection notation.

        :param edge: Dictionary representing an edge.
        :return: Mermaid edge definition string.
        """
        src = "N" + edge["source"]
        tgt = "N" + edge["target"]
        label = edge["label"].strip()
        style = edge["style_dict"]

        # Default arrow is solid directed arrow
        arrow = "-->"
        if style.get("dashed") or style.get("dashed") == "1":
            arrow = "-.->"
        if style.get("endArrow") == "none":
            arrow = arrow.replace("->", "-")

        if label:
            edge_def = f'{src} -- "{label}" {arrow} {tgt}'
        else:
            edge_def = f'{src} {arrow} {tgt}'
        return edge_def

    # --- Emitting Mermaid Syntax ---
    def _emit_subgraph_recursive(self, group_id, group, indent_level=0):
        """
        Recursively emits a subgraph for a group and any nested groups.

        :param group_id: The group identifier.
        :param group: Dictionary with keys "label" and "children".
        :param indent_level: Current indentation level (for formatting).
        :return: A list of Mermaid syntax lines for this subgraph.
        """
        indent = "    " * indent_level
        lines = []
        lines.append(f"{indent}subgraph {group_id}[{group['label']}]")
        # Emit child nodes first
        for child in group.get("children", []):
            # Check if this child itself is a group container.
            child_id = child["id"]
            if child_id in self.diagram["groups"]:
                # Recursive call for nested group.
                nested_group = self.diagram["groups"][child_id]
                lines.extend(self._emit_subgraph_recursive(child_id, nested_group, indent_level + 1))
            else:
                try:
                    node_def = self._format_node(child)
                    lines.append(f"{indent}    {node_def}")
                except Exception as e:
                    self.logger.warning(f"Error formatting node {child_id} in group {group_id}: {str(e)}")
        lines.append(f"{indent}end")
        return lines

    def _emit_mermaid(self, diagram, direction="TD", diagram_type="flowchart"):
        """
        Converts the internal diagram representation into Mermaid code.

        Currently supports 'flowchart' diagram_type.
        :param diagram: Dictionary containing nodes, edges, and groups.
        :param direction: Mermaid flow direction (e.g., TD for top-down, LR for left-right).
        :param diagram_type: Type of Mermaid diagram to emit.
        :return: Mermaid code as a string.
        """
        lines = []
        if diagram_type == "flowchart":
            lines.append(f"flowchart {direction}")
        else:
            self.logger.warning(f"Diagram type '{diagram_type}' not fully supported. Defaulting to flowchart.")
            lines.append(f"flowchart {direction}")

        nodes_emitted = set()

        # Emit groups (subgraphs) recursively
        for group_id, group in diagram.get("groups", {}).items():
            try:
                group_lines = self._emit_subgraph_recursive(group_id, group, indent_level=0)
                lines.extend(group_lines)
                for child in group.get("children", []):
                    nodes_emitted.add(child["id"])
            except Exception as e:
                self.logger.warning(f"Error emitting subgraph for group {group_id}: {str(e)}")

        # Emit nodes not in any group
        for node in diagram.get("nodes", []):
            if node["id"] not in nodes_emitted:
                try:
                    node_def = self._format_node(node)
                    lines.append(node_def)
                except Exception as e:
                    self.logger.warning(f"Error formatting node {node['id']}: {str(e)}")

        # Emit edges
        for edge in diagram.get("edges", []):
            try:
                if edge["source"] not in self.node_map or edge["target"] not in self.node_map:
                    self.logger.warning(f"Skipping edge {edge['id']} due to missing endpoints.")
                    continue
                edge_def = self._format_edge(edge)
                lines.append(edge_def)
            except Exception as e:
                self.logger.warning(f"Error formatting edge {edge['id']}: {str(e)}")

        return "\n".join(lines)

    # --- Main Conversion Method ---
    def convert(self, input_data, diagram_index=0, direction="TD", diagram_type="flowchart"):
        """
        Main method to convert Draw.io XML data to Mermaid code.

        :param input_data: Raw content of the Draw.io file.
        :param diagram_index: Which diagram page to convert (default: 0).
        :param direction: Flow direction for Mermaid (e.g., "TD", "LR").
        :param diagram_type: The type of Mermaid diagram to emit (default: "flowchart").
        :return: Mermaid code as a string.
        :raises Exception: In strict mode, conversion errors will propagate.
        """
        try:
            self.logger.info("Starting conversion process.")
            self.diagram_pages = []
            self._decompress_data(input_data)
            if not self.diagram_pages:
                msg = "No valid diagram pages found."
                self.logger.error(msg)
                if self.strict_mode:
                    raise DiagramDecompressionError(msg)
                else:
                    return ""

            if diagram_index < 0 or diagram_index >= len(self.diagram_pages):
                msg = f"Diagram index {diagram_index} out of range. Available indices: 0 to {len(self.diagram_pages)-1}."
                self.logger.error(msg)
                if self.strict_mode:
                    raise IndexError(msg)
                else:
                    diagram_index = 0

            xml_diagram = self.diagram_pages[diagram_index]
            root = self._parse_xml(xml_diagram)
            if root is None:
                return ""
            diagram = self._build_diagram_from_root(root)
            mermaid_code = self._emit_mermaid(diagram, direction=direction, diagram_type=diagram_type)
            self.logger.info("Conversion completed successfully.")
            return mermaid_code
        except Exception as e:
            self.logger.error("Conversion failed: " + str(e))
            if self.strict_mode:
                raise
            else:
                return ""


# --- Example Usage ---
if __name__ == "__main__":
    import sys

    # Configure logging at DEBUG level for detailed output
    converter = FlowForgeConverter(log_level=logging.DEBUG, strict_mode=False)
    try:
        file_path = "example.drawio"  # Replace with your Draw.io file path.
        xml_content = converter.load_file(file_path)
        pages = converter.list_diagram_pages(xml_content)
        print(f"Available diagram pages: {pages}")
        mermaid_output = converter.convert(xml_content, diagram_index=0, direction="LR", diagram_type="flowchart")
        print("=== Mermaid Diagram ===")
        print(mermaid_output)
    except Exception as error:
        sys.exit(f"An error occurred during conversion: {error}")


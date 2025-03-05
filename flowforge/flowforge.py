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
import gzip
import re
import logging
import binascii
from urllib.parse import unquote


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
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(log_level)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

        self.strict_mode = strict_mode
        self.node_map = {}
        self.diagram = {"nodes": [], "edges": [], "groups": {}}
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
        it assumes the content inside <diagram> is compressed (base64 + deflate).
        In relaxed mode, tries multiple known wbits parameters to handle variations
        in compression headers (raw deflate, zlib, gzip) and then a gzip fallback.

        Populates self.diagram_pages with decompressed XML strings.
        """
        if "<mxGraphModel" in xml_data:
            self.logger.debug("Found uncompressed <mxGraphModel> tag directly in the file.")
            self.diagram_pages.append(xml_data)
            return

        # Handle compressed data
        diagrams = re.findall(r"<diagram[^>]*>(.*?)</diagram>", xml_data, re.DOTALL)
        
        if not diagrams:
            self.logger.debug("No <diagram> tags found. Checking if entire file is an mxfile.")
            # Try parsing as mxfile directly - some files use mxfile as root element
            try:
                root = ET.fromstring(xml_data)
                if root.tag == 'mxfile':
                    self.logger.debug("File is an mxfile. Extracting diagrams.")
                    for diagram in root.findall('diagram'):
                        diagram_content = diagram.text if diagram.text else ""
                        diagrams.append(diagram_content)
            except ET.ParseError as e:
                self.logger.debug(f"Failed to parse XML looking for mxfile: {str(e)}")
        
        if diagrams:
            self.logger.debug(f"Found {len(diagrams)} <diagram> tag(s). Attempting decompression.")
            for d_index, d in enumerate(diagrams):
                d = d.strip()
                is_decompressed = False
                
                if not d:  # Skip empty diagram data
                    self.logger.warning(f"Diagram {d_index} is empty. Skipping.")
                    continue
                
                # Try direct XML parse if it looks like uncompressed XML
                if d.startswith('<') and '<mxGraphModel' in d:
                    self.logger.debug(f"Diagram {d_index} appears to be uncompressed XML. Adding directly.")
                    self.diagram_pages.append(d)
                    continue
                
                # Try URL decoding first (some draw.io files use URL encoding)
                try:
                    d_decoded = unquote(d)
                    if '<mxGraphModel' in d_decoded:
                        self.logger.debug(f"Diagram {d_index} was URL encoded. Adding decoded version.")
                        self.diagram_pages.append(d_decoded)
                        continue
                except Exception as e:
                    self.logger.debug(f"URL decoding attempt failed: {str(e)}")
                
                # Try base64 decoding
                try:
                    # Handle padding issues - draw.io might not include proper padding
                    padding_needed = len(d) % 4
                    if padding_needed:
                        d += '=' * (4 - padding_needed)
                    
                    # Try to decode as base64
                    try:
                        decoded = base64.b64decode(d)
                    except binascii.Error:
                        # Sometimes drawio uses urlsafe base64
                        try:
                            decoded = base64.urlsafe_b64decode(d)
                        except binascii.Error as e:
                            self.logger.debug(f"Both standard and urlsafe base64 decoding failed: {str(e)}")
                            raise
                except Exception as e:
                    self.logger.error(f"Base64 decoding failed for diagram {d_index}: {str(e)}")
                    if self.strict_mode:
                        raise DiagramDecompressionError(str(e))
                    else:
                        continue

                # Check if it's already XML (uncompressed but base64 encoded)
                try:
                    xml_check = decoded.decode('utf-8', errors='ignore')
                    if xml_check.startswith('<') and '<mxGraphModel' in xml_check:
                        self.logger.debug(f"Diagram {d_index} was base64 encoded XML. Adding decoded version.")
                        self.diagram_pages.append(xml_check)
                        is_decompressed = True
                        continue
                except UnicodeDecodeError:
                    # Not UTF-8 text, continue with decompression attempts
                    pass

                # Try various decompression methods
                decompression_attempts = [
                    # (wbits, description)
                    (-15, "raw deflate"),
                    (47, "deflate with zlib header & 32k window"),
                    (31, "deflate with zlib header & 16k window"),
                    (15, "deflate with zlib header & 8k window"),
                    (0, "auto-detect zlib/gzip header")
                ]
                
                for wbits, desc in decompression_attempts:
                    if is_decompressed:
                        break
                    try:
                        if wbits == 0:
                            # Auto-detect header
                            decompressed = zlib.decompress(decoded, zlib.MAX_WBITS | 32)
                        else:
                            decompressed = zlib.decompress(decoded, wbits)
                        
                        xml_text = decompressed.decode('utf-8', errors='replace')
                        if "<mxGraphModel" in xml_text:
                            self.diagram_pages.append(xml_text)
                            self.logger.info(f"Successfully decompressed diagram {d_index} using {desc}.")
                            is_decompressed = True
                        else:
                            self.logger.warning(
                                f"Decompression with {desc} succeeded, but no <mxGraphModel> found in diagram {d_index}."
                            )
                    except Exception as e:
                        self.logger.debug(f"Decompression attempt with {desc} failed: {str(e)}")
                
                # Try gzip if still not decompressed and it looks like gzip
                if not is_decompressed and len(decoded) >= 2 and decoded[:2] == b'\x1f\x8b':
                    try:
                        decompressed = gzip.decompress(decoded)
                        xml_text = decompressed.decode('utf-8', errors='replace')
                        if "<mxGraphModel" in xml_text:
                            self.diagram_pages.append(xml_text)
                            self.logger.info(f"Successfully decompressed diagram {d_index} using gzip.")
                            is_decompressed = True
                        else:
                            self.logger.warning(f"Gzip decompression succeeded, but no <mxGraphModel> found in diagram {d_index}.")
                    except Exception as e:
                        self.logger.debug(f"Gzip decompression attempt failed: {str(e)}")
                
                # Try PAKO/PAKO 0.2.0 variant (some newer draw.io files)
                if not is_decompressed:
                    try:
                        inflator = zlib.decompressobj(16 + zlib.MAX_WBITS)
                        decompressed = inflator.decompress(decoded)
                        xml_text = decompressed.decode('utf-8', errors='replace')
                        if "<mxGraphModel" in xml_text:
                            self.diagram_pages.append(xml_text)
                            self.logger.info(f"Successfully decompressed diagram {d_index} using PAKO variant.")
                            is_decompressed = True
                    except Exception as e:
                        self.logger.debug(f"PAKO variant decompression attempt failed: {str(e)}")
                
                # Last resort: try to interpret as plain XML even if it looks like garbage
                if not is_decompressed and not self.strict_mode:
                    try:
                        # Just a sanity check - see if there's any XML-like content
                        cleaned = re.sub(r'[^\x20-\x7E]', '', decoded.decode('latin-1', errors='ignore'))
                        if '<' in cleaned and '>' in cleaned:
                            self.logger.warning(f"Diagram {d_index} couldn't be properly decompressed but contains XML-like content. Attempting to process.")
                            self.diagram_pages.append(cleaned)
                            is_decompressed = True
                    except Exception as e:
                        self.logger.debug(f"Last resort XML interpretation failed: {str(e)}")
                
                if not is_decompressed:
                    msg = (
                        f"Failed to decompress diagram {d_index} with all known parameters. "
                        "Likely corrupt or unsupported compression format."
                    )
                    self.logger.error(msg)
                    if self.strict_mode:
                        raise DiagramDecompressionError(msg)
                    # In relaxed mode, skip this diagram page
        else:
            self.logger.debug("No <diagram> tags or mxfile format detected.")
            # Last attempt: check if it's a plain XML file with mxGraphModel
            if "<mxGraphModel" in xml_data:
                self.diagram_pages.append(xml_data)
                self.logger.info("Found uncompressed mxGraphModel in the input.")
            else:
                msg = "Input data does not contain valid Draw.io XML, <diagram> tags, or an mxfile."
                self.logger.error(msg)
                if self.strict_mode:
                    raise DiagramDecompressionError(msg)

    def list_diagram_pages(self, xml_data):
        """
        Parses the raw file content and returns a list of diagram page indices.

        :param xml_data: The raw file content.
        :return: List of indices representing available diagram pages.
        """
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
            # Try to clean up any potential XML issues before parsing
            xml_data = xml_data.replace('&nbsp;', '&#160;')  # Common in draw.io files
            
            # Handle XML declaration if missing
            if not xml_data.strip().startswith('<?xml') and '<mxGraphModel' in xml_data:
                xml_data = '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_data
            
            # If we only have the mxGraphModel part, wrap it
            if xml_data.strip().startswith('<mxGraphModel') and not xml_data.strip().startswith('<diagram'):
                xml_data = f'<diagram>{xml_data}</diagram>'
            
            root = ET.fromstring(xml_data)
            
            # If root is diagram, get the mxGraphModel inside it
            if root.tag == 'diagram':
                for child in root:
                    if child.tag == 'mxGraphModel':
                        root = child
                        break
            # If root is mxfile, find the first diagram and its mxGraphModel
            elif root.tag == 'mxfile':
                diagram = root.find('diagram')
                if diagram is not None:
                    # Check if mxGraphModel is a child or encoded in text
                    mx_model = diagram.find('mxGraphModel')
                    if mx_model is not None:
                        root = mx_model
            
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
        self.node_map = {}
        self.diagram = {"nodes": [], "edges": [], "groups": {}}

        # If we're starting from a diagram tag, find the mxGraphModel
        if root.tag == 'diagram':
            model = root.find('mxGraphModel')
            if model is not None:
                root = model
        
        diagram_root = root.find("root")
        if diagram_root is None:
            # Some versions might have cells directly under mxGraphModel
            diagram_root = root
            
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

        for node in self.diagram["nodes"]:
            parent = node.get("parent")
            if parent and parent in self.node_map:
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
        node_id = "N" + node["id"]

        shape = style.get("shape", "").lower()
        if shape == "rhombus":
            node_def = f'{node_id}{{"{label}"}}'
        elif shape == "ellipse" or "ellipse" in style:
            node_def = f'{node_id}(( "{label}" ))'
        elif style.get("rounded") == "1" or shape == "stadium":
            node_def = f'{node_id}("{label}")'
        else:
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
        for child in group.get("children", []):
            child_id = child["id"]
            if child_id in self.diagram["groups"]:
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

        for group_id, group in diagram.get("groups", {}).items():
            try:
                group_lines = self._emit_subgraph_recursive(group_id, group, indent_level=0)
                lines.extend(group_lines)
                for child in group.get("children", []):
                    nodes_emitted.add(child["id"])
            except Exception as e:
                self.logger.warning(f"Error emitting subgraph for group {group_id}: {str(e)}")

        for node in diagram.get("nodes", []):
            if node["id"] not in nodes_emitted:
                try:
                    node_def = self._format_node(node)
                    lines.append(node_def)
                except Exception as e:
                    self.logger.warning(f"Error formatting node {node['id']}: {str(e)}")

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

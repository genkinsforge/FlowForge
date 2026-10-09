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
import html
import unicodedata
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


def clean_label(label, is_html=False):
    """
    Convert a Draw.io label into text that is safe inside a quoted Mermaid label.

    When the cell style has html=1, Draw.io stores the label as HTML markup
    (e.g. '<font color="#ff0000">Start</font>'). Formatting tags are stripped,
    line breaks (<br>, <div>, <p>, newlines) are joined with a single space,
    and HTML entities are decoded. Characters that would break Mermaid syntax are
    then escaped using Mermaid entity codes.

    :param label: Raw label string from a Draw.io cell's "value" attribute.
    :param is_html: True if the cell's style has html=1.
    :return: Cleaned label string.
    """
    if not label:
        return ""
    text = label
    if is_html:
        text = re.sub(r'<\s*br\s*/?\s*>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'<\s*/?\s*(div|p)\b[^>]*>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'<[^>]*>', '', text)
        text = html.unescape(text)
    text = text.replace('\xa0', ' ')
    text = re.sub(r'\s+', ' ', text).strip()
    return (text.replace('#', '#35;')
                .replace('"', '#quot;')
                .replace('<', '#lt;')
                .replace('>', '#gt;'))


# Draw.io "shape=" values mapped to Mermaid node shapes. Each entry is the
# (opening, closing) bracket pair placed around the quoted label.
SHAPE_BRACKETS = {
    "rhombus": ("{", "}"),
    "mxgraph.flowchart.decision": ("{", "}"),
    "hexagon": ("{{", "}}"),
    "mxgraph.flowchart.preparation": ("{{", "}}"),
    "cylinder": ("[(", ")]"),
    "cylinder3": ("[(", ")]"),
    "datastore": ("[(", ")]"),
    "mxgraph.flowchart.database": ("[(", ")]"),
    "mxgraph.flowchart.stored_data": ("[(", ")]"),
    "parallelogram": ("[/", "/]"),
    "mxgraph.flowchart.data": ("[/", "/]"),
    "trapezoid": ("[/", "\\]"),
    "mxgraph.flowchart.manual_operation": ("[\\", "/]"),
    "process": ("[[", "]]"),
    "mxgraph.flowchart.predefined_process": ("[[", "]]"),
    "mxgraph.flowchart.terminator": ("([", "])"),
    "doubleellipse": ("(((", ")))"),
    "ellipse": ("((", "))"),
    "mxgraph.flowchart.start_1": ("((", "))"),
    "mxgraph.flowchart.start_2": ("((", "))"),
}

# Style flags (style keys without a value) mapped to Mermaid node shapes. Only
# used when the style has no "shape=" entry; e.g. clouds are "ellipse;shape=cloud".
FLAG_BRACKETS = {
    "rhombus": ("{", "}"),
    "ellipse": ("((", "))"),
}

# Draw.io "shape=" values that are drawn as rectangles, so mapping them to a Mermaid
# rectangle loses nothing. Any other unmapped shape (and the "triangle" style flag)
# is reported as simplified.
RECTANGLE_SHAPES = {"rect", "rectangle", "label", "mxgraph.flowchart.process"}

# Draw.io arrowhead styles and the Mermaid marker each maps to. Any other style
# (diamond, ER notation, half circle, ...) is drawn as a normal arrow and reported.
ARROW_MARKERS = {
    "none": "",
    "classic": ">", "classicThin": ">", "block": ">", "blockThin": ">",
    "open": ">", "openThin": ">",
    "oval": "o", "ovalThin": "o", "circle": "o", "circlePlus": "o",
    "cross": "x",
}

# Words that cannot be used as Mermaid flowchart node IDs.
MERMAID_RESERVED_IDS = {
    "end", "graph", "flowchart", "subgraph", "direction", "style", "class",
    "classdef", "click", "linkstyle", "default", "call", "href",
}


def slugify(label, max_length=40):
    """
    Turn a cleaned label into a Mermaid-safe identifier, e.g. "Capacity List" -> "capacity_list".

    :param label: Label as returned by clean_label().
    :param max_length: Longest slug to produce; longer slugs are cut at a word boundary.
    :return: Lowercase identifier of letters, digits and underscores, or "" if none remain.
    """
    text = re.sub(r'#\w+;', ' ', label)  # drop Mermaid entity codes such as #quot;
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
    slug = re.sub(r'[^a-z0-9]+', '_', text.lower()).strip('_')
    if len(slug) > max_length:
        slug = slug[:max_length].rsplit('_', 1)[0]
    return slug


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
        self.mermaid_ids = {}
        self.skipped_ids = set()
        self.simplified = {"shapes": set(), "edges": set()}

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
        # Split into pages first; each page may be compressed or plain XML.
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
                        # draw.io URL-encodes the XML before deflating it.
                        if "<mxGraphModel" not in xml_text:
                            xml_text = unquote(xml_text)
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
                        # draw.io URL-encodes the XML before deflating it.
                        if "<mxGraphModel" not in xml_text:
                            xml_text = unquote(xml_text)
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
                        # draw.io URL-encodes the XML before deflating it.
                        if "<mxGraphModel" not in xml_text:
                            xml_text = unquote(xml_text)
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
                style = cell.get("style") or ""
                style_dict = parse_style(style)
                label = clean_label(cell.get("value") or "", style_dict.get("html") == "1")
                geometry = cell.find("mxGeometry")
                node = {
                    "id": cell_id,
                    "label": label,
                    "style": style,
                    "style_dict": style_dict,
                    "geometry": geometry.attrib if geometry is not None else {},
                    "parent": cell.get("parent")
                }
                self.diagram["nodes"].append(node)
                self.node_map[cell_id] = node

            elif cell.get("edge") == "1":
                style = cell.get("style") or ""
                style_dict = parse_style(style)
                edge = {
                    "id": cell_id,
                    "source": cell.get("source"),
                    "target": cell.get("target"),
                    "label": clean_label(cell.get("value") or "", style_dict.get("html") == "1"),
                    "style": style,
                    "style_dict": style_dict
                }
                self.diagram["edges"].append(edge)
            else:
                self.logger.debug(f"Skipping cell id {cell_id}: not a vertex or edge.")

        # Cells with custom properties (Edit Data), links or tooltips are wrapped in
        # <object> or <UserObject> elements. These are not supported yet.
        self.skipped_ids = set()
        for wrapper in diagram_root:
            if wrapper.tag not in ("object", "UserObject"):
                continue
            wrapper_id = wrapper.get("id")
            self.skipped_ids.add(wrapper_id)
            label = clean_label(wrapper.get("label") or "", True)
            self.logger.warning(
                f"Skipping shape '{label}' (id {wrapper_id}): shapes with custom properties, "
                "links or tooltips are not supported."
            )

        # Labels added to an edge in Draw.io are stored as child vertices of that
        # edge. Merge them into the edge's label instead of emitting stray nodes.
        edge_map = {edge["id"]: edge for edge in self.diagram["edges"]}
        for node in list(self.diagram["nodes"]):
            edge = edge_map.get(node.get("parent"))
            if edge is None:
                continue
            if node["label"]:
                edge["label"] = " ".join(l for l in (edge["label"], node["label"]) if l)
            self.diagram["nodes"].remove(node)
            del self.node_map[node["id"]]

        self.logger.info("Built diagram: %d nodes, %d edges.",
                         len(self.diagram["nodes"]), len(self.diagram["edges"]))

        for node in self.diagram["nodes"]:
            parent = node.get("parent")
            if parent and parent in self.node_map:
                parent_style = self.node_map[parent].get("style", "")
                is_container = self.node_map[parent]["style_dict"].get("container") == "1"
                if is_container or "group" in parent_style or "swimlane" in parent_style:
                    if parent not in self.diagram["groups"]:
                        self.diagram["groups"][parent] = {
                            "label": self.node_map[parent].get("label") or " ",
                            "children": []
                        }
                    self.diagram["groups"][parent]["children"].append(node)
        return self.diagram

    # --- Node and Edge Formatting ---
    def _mermaid_id(self, cell_id):
        """Returns the Mermaid identifier for a Draw.io cell ID."""
        return self.mermaid_ids.get(cell_id, "N" + cell_id)

    def _assign_readable_ids(self, diagram):
        """
        Builds self.mermaid_ids, mapping each node and group to an identifier made
        from its label instead of the random Draw.io cell ID.

        A label used by only one cell becomes its ID ("Treasury" -> treasury).
        Repeated labels are prefixed with the enclosing group's ID
        ("Capacity List" in group "Law" -> law_capacity_list), and any that
        still clash are numbered in document order (social_stance_list_stance_1, _2, ...).
        Groups are named before their contents so prefixes match the group IDs.

        :param diagram: Dictionary containing nodes, edges, and groups.
        """
        nodes = diagram.get("nodes", [])
        base = {}
        for node in nodes:
            slug = slugify(node["label"]) or ("group" if node["id"] in diagram.get("groups", {}) else "node")
            if slug[0].isdigit():
                slug = "n_" + slug
            if slug in MERMAID_RESERVED_IDS:
                slug += "_node"
            base[node["id"]] = slug

        base_counts = {}
        for slug in base.values():
            base_counts[slug] = base_counts.get(slug, 0) + 1

        def depth(node_id):
            level = 0
            parent = self.node_map[node_id].get("parent")
            while parent in base:
                level += 1
                parent = self.node_map[parent].get("parent")
            return level

        levels = {}
        for node in nodes:
            levels.setdefault(depth(node["id"]), []).append(node["id"])

        self.mermaid_ids = {}
        taken = set()
        for level in sorted(levels):
            candidates = {}
            for node_id in levels[level]:
                slug = base[node_id]
                parent = self.node_map[node_id].get("parent")
                if base_counts[slug] > 1 and parent in self.mermaid_ids:
                    slug = f"{self.mermaid_ids[parent]}_{slug}"
                candidates[node_id] = slug
            counts = {}
            for slug in candidates.values():
                counts[slug] = counts.get(slug, 0) + 1
            for node_id, slug in candidates.items():
                if counts[slug] == 1 and slug not in taken:
                    self.mermaid_ids[node_id] = slug
                    taken.add(slug)
            numbers = {}
            for node_id, slug in candidates.items():
                if node_id in self.mermaid_ids:
                    continue
                while True:
                    numbers[slug] = numbers.get(slug, 0) + 1
                    numbered = f"{slug}_{numbers[slug]}"
                    if numbered not in taken and counts.get(numbered, 0) == 0:
                        break
                self.mermaid_ids[node_id] = numbered
                taken.add(numbered)

    def _format_node(self, node):
        """
        Converts a single node from the internal representation to its Mermaid node definition.
        It uses the parsed style dictionary to choose the correct shape.

        :param node: Dictionary representing a node.
        :return: Mermaid node definition string.
        """
        label = node["label"].strip() if node["label"] else f"Node_{node['id']}"
        style = node["style_dict"]
        node_id = self._mermaid_id(node["id"])

        shape = style.get("shape", "").lower()
        flag = None if shape else next((f for f in FLAG_BRACKETS if f in style), None)
        if shape in SHAPE_BRACKETS:
            opening, closing = SHAPE_BRACKETS[shape]
        elif flag:
            opening, closing = FLAG_BRACKETS[flag]
        elif style.get("rounded") == "1":
            opening, closing = "(", ")"
        else:
            opening, closing = "[", "]"
            if shape:
                unmapped = None if shape in RECTANGLE_SHAPES else shape
            else:
                unmapped = "triangle" if "triangle" in style else None
            if unmapped:
                self._note_simplified("shapes", node["id"], f"shape '{label}'",
                                      f"draw.io shape '{unmapped}' has no Mermaid equivalent; drawn as a rectangle")
        return f'{node_id}{opening}"{label}"{closing}'

    def _format_edge(self, edge):
        """
        Converts a single edge into Mermaid connection notation.

        :param edge: Dictionary representing an edge.
        :return: Mermaid edge definition string.
        """
        src = self._mermaid_id(edge["source"])
        tgt = self._mermaid_id(edge["target"])
        label = edge["label"].strip()
        style = edge["style_dict"]

        source_label = self.node_map[edge["source"]]["label"] or edge["source"]
        target_label = self.node_map[edge["target"]]["label"] or edge["target"]
        description = f"edge '{source_label}' -> '{target_label}'"

        # Draw.io draws an arrowhead at the end and none at the start unless told otherwise.
        end_style = style.get("endArrow", "classic")
        start_style = style.get("startArrow", "none")
        for arrow_style in (start_style, end_style):
            if arrow_style not in ARROW_MARKERS:
                self._note_simplified("edges", edge["id"], description,
                                      f"arrowhead '{arrow_style}' has no Mermaid equivalent; drawn as a normal arrow")
        end = ARROW_MARKERS.get(end_style, ">")
        start = ARROW_MARKERS.get(start_style, ">")
        if start and not end:
            # Arrowhead only at the start: reverse the edge so Mermaid can draw it.
            src, tgt, start, end = tgt, src, "", start
        elif start and start != end:
            # Mermaid can only draw matching markers at both ends.
            self._note_simplified("edges", edge["id"], description,
                                  f"different markers at each end ({start_style}, {end_style}); "
                                  "only the end marker is kept")
            start = ""

        try:
            thick = float(style.get("strokeWidth", 1)) >= 3
        except ValueError:
            thick = False
        if style.get("dashed") in ("1", True):
            line, plain_line = "-.-", "-.-"
            if thick:
                self._note_simplified("edges", edge["id"], description,
                                      "thick dashed line drawn as a normal dashed line (Mermaid has no thick dashed line)")
        elif thick:
            line, plain_line = "==", "==="
        else:
            line, plain_line = "--", "---"
        if end:
            arrow = {"": "", ">": "<", "o": "o", "x": "x"}[start] + line + end
        else:
            arrow = plain_line

        if label:
            edge_def = f'{src} {arrow}|"{label}"| {tgt}'
        else:
            edge_def = f'{src} {arrow} {tgt}'
        return edge_def

    def _note_simplified(self, kind, item_id, description, reason):
        """
        Records that a shape or edge could not be reproduced exactly in Mermaid.
        Details are logged at INFO level; _emit_mermaid logs a one-line summary as a warning.

        :param kind: "shapes" or "edges".
        :param item_id: Draw.io cell ID, so an item with several problems is counted once.
        :param description: Human-readable name of the item, e.g. "shape 'Treasury'".
        :param reason: What was simplified.
        """
        self.simplified[kind].add(item_id)
        self.logger.info(f"Simplified {description} (id {item_id}): {reason}")

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
        label = group["label"]
        lines.append(f'{indent}subgraph {self._mermaid_id(group_id)}["{label}"]')
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

    def _emit_mermaid(self, diagram, direction="TD", diagram_type="flowchart", readable_ids=True):
        """
        Converts the internal diagram representation into Mermaid code.

        Currently supports 'flowchart' diagram_type.
        :param diagram: Dictionary containing nodes, edges, and groups.
        :param direction: Mermaid flow direction (e.g., TD for top-down, LR for left-right).
        :param diagram_type: Type of Mermaid diagram to emit.
        :param readable_ids: Use IDs made from labels instead of Draw.io cell IDs.
        :return: Mermaid code as a string.
        """
        self.mermaid_ids = {}
        self.simplified = {"shapes": set(), "edges": set()}
        if readable_ids:
            self._assign_readable_ids(diagram)

        lines = []
        if diagram_type == "flowchart":
            lines.append(f"flowchart {direction}")
        else:
            self.logger.warning(f"Diagram type '{diagram_type}' not fully supported. Defaulting to flowchart.")
            lines.append(f"flowchart {direction}")

        groups = diagram.get("groups", {})
        # Group nodes are emitted as subgraphs, never as plain nodes.
        nodes_emitted = set(groups)

        for group_id, group in groups.items():
            # Nested groups are emitted by their parent's subgraph.
            if self.node_map[group_id].get("parent") in groups:
                continue
            try:
                group_lines = self._emit_subgraph_recursive(group_id, group, indent_level=0)
                lines.extend(group_lines)
            except Exception as e:
                self.logger.warning(f"Error emitting subgraph for group {group_id}: {str(e)}")
        for group in groups.values():
            for child in group.get("children", []):
                nodes_emitted.add(child["id"])

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
                    if {edge["source"], edge["target"]} & self.skipped_ids:
                        self.logger.warning(f"Skipping edge {edge['id']}: it connects to a skipped shape.")
                    else:
                        self.logger.warning(f"Skipping edge {edge['id']} due to missing endpoints.")
                    continue
                edge_def = self._format_edge(edge)
                lines.append(edge_def)
            except Exception as e:
                self.logger.warning(f"Error formatting edge {edge['id']}: {str(e)}")

        edge_count, shape_count = len(self.simplified["edges"]), len(self.simplified["shapes"])
        if edge_count or shape_count:
            parts = [f"{n} {kind[:-1] if n == 1 else kind}"
                     for n, kind in ((edge_count, "edges"), (shape_count, "shapes")) if n]
            verb = "was" if edge_count + shape_count == 1 else "were"
            self.logger.warning(f"{' and '.join(parts)} {verb} simplified to fit Mermaid; "
                                "run with -v (or log level INFO) for details.")

        return "\n".join(lines)

    # --- Main Conversion Method ---
    def convert(self, input_data, diagram_index=0, direction="TD", diagram_type="flowchart",
                readable_ids=True):
        """
        Main method to convert Draw.io XML data to Mermaid code.

        :param input_data: Raw content of the Draw.io file.
        :param diagram_index: Which diagram page to convert (default: 0).
        :param direction: Flow direction for Mermaid (e.g., "TD", "LR").
        :param diagram_type: The type of Mermaid diagram to emit (default: "flowchart").
        :param readable_ids: Use node IDs made from labels (e.g. capacity_list) instead of
                             Draw.io cell IDs (default: True).
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
            mermaid_code = self._emit_mermaid(diagram, direction=direction, diagram_type=diagram_type,
                                              readable_ids=readable_ids)
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

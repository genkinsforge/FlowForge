# FlowForge

**FlowForge** is a robust and extensible Python framework for converting Draw.io (Diagram.net) diagrams to Mermaid diagrams. This library supports multi-page diagrams, enhanced style parsing, recursive group/subgraph handling, and configurable logging with error correction modes.

> **Note:** This project is released under the [MIT License](LICENSE) with the requirement that credit is given to **Genkins Forge LLC**.

[GitHub Repository](https://github.com/genkinsforge/FlowForge)

---

## Table of Contents

- [Features](#features)
- [Installation](#installation)
- [Usage](#usage)
- [Supported Draw.io Elements](#supported-drawio-elements)
- [API Overview](#api-overview)
- [Logging & Configuration](#logging--configuration)
- [License](#license)
- [Contributing](#contributing)
- [Credits](#credits)

---

## Features

- **Multi-Page Support:**  
  Automatically detects and processes multiple `<diagram>` tags in a Draw.io file.

- **Enhanced Style Parsing:**  
  Converts Draw.io style strings into dictionaries for fine-grained mapping of shapes and arrow styles.

- **Recursive Group/Subgraph Handling:**  
  Supports nested groups (swimlanes or container nodes) and emits recursive subgraphs in the Mermaid output.

- **Robust Error Handling:**  
  Configurable strict or relaxed modes ensure that conversion issues are either logged as warnings or cause process termination.

- **Extensible & Modular:**  
  Designed for easy extension to additional diagram types (e.g., mind maps, sequence diagrams) and improved style parsing.

- **Multi-Level Logging:**  
  Integrated logging (DEBUG, INFO, WARNING, ERROR) to assist with development, debugging, and production use.

---

## Installation

You can install FlowForge directly from PyPI:

```bash
pip install flowforge
```

Alternatively, if you want to install FlowForge from the source:

1. Clone the repository:

    ```bash
    git clone https://github.com/genkinsforge/FlowForge.git
    cd FlowForge
    ```

2. Install FlowForge using pip:

    ```bash
    pip install .
    ```

*Note: FlowForge is built entirely on Python's standard library, so no external dependencies are required.*

---

## Usage

### Command Line

Convert a Draw.io file to a Markdown file containing Mermaid code blocks:

```bash
python -m flowforge diagram            # reads diagram.drawio, writes diagram.md
flowforge diagram.drawio -o out.md     # same, when installed with pip
```

If no extension is given, `.drawio` is assumed. All diagram pages are converted, each under its own heading. Options:

- `-o, --output`: output path (default: the input name with a `.md` extension)
- `--index N`: convert only page `N`
- `--direction TD|LR|...`: Mermaid flow direction (default: `TD`)
- `--drawio-ids`: use Draw.io's cell IDs as node IDs (`N65PPJ_XJzwb0lOGMphRH-12`). By default, IDs are built from labels (`law_capacity_list`); repeated labels are prefixed with their group's ID, then numbered if still ambiguous.
- `--strict`: stop on the first conversion error
- `-v, --verbose`: show detailed conversion logging

### Python API

Below is an example of how to use FlowForge in your Python code:

```python
import logging
from flowforge import FlowForgeConverter

# Initialize FlowForgeConverter with DEBUG logging and relaxed error handling.
converter = FlowForgeConverter(log_level=logging.DEBUG, strict_mode=False)

# Load a Draw.io file (e.g., "example.drawio")
xml_content = converter.load_file("example.drawio")

# List available diagram pages.
pages = converter.list_diagram_pages(xml_content)
print("Available diagram pages:", pages)

# Convert the first page (index 0) to a left-to-right Mermaid flowchart.
mermaid_code = converter.convert(xml_content, diagram_index=0, direction="LR", diagram_type="flowchart")
print("=== Generated Mermaid Diagram ===")
print(mermaid_code)
```

This script loads a Draw.io diagram file, lists the available pages, and converts the first diagram page into Mermaid flowchart syntax.

---

## Supported Draw.io Elements

FlowForge produces Mermaid flowcharts, so each Draw.io shape is mapped to the closest Mermaid flowchart shape. Shapes without a Mermaid equivalent become plain rectangles; their labels and connections are kept.

Whenever a shape or edge has to be simplified (an unmapped shape, an arrowhead Mermaid can't draw, different markers at each end, or a thick dashed line), FlowForge prints a one-line warning per page, e.g. `2 edges and 3 shapes were simplified to fit Mermaid`. Run with `-v` to list each simplified item and the reason.

### Shapes

| Draw.io shape | Style | Mermaid shape |
|---|---|---|
| Rectangle, square, text | *(default)* | `["…"]` rectangle |
| Rounded rectangle | `rounded=1` | `("…")` rounded rectangle |
| Ellipse, circle, flowchart start | `ellipse`, `shape=mxgraph.flowchart.start_1/2` | `(("…"))` circle |
| Double ellipse | `shape=doubleEllipse` | `((("…")))` double circle |
| Diamond, flowchart decision | `rhombus`, `shape=mxgraph.flowchart.decision` | `{"…"}` diamond |
| Hexagon, flowchart preparation | `shape=hexagon`, `shape=mxgraph.flowchart.preparation` | `{{"…"}}` hexagon |
| Cylinder, data store, flowchart database / stored data | `shape=cylinder3`, `shape=datastore`, `shape=mxgraph.flowchart.database` | `[("…")]` cylinder |
| Parallelogram, flowchart data | `shape=parallelogram`, `shape=mxgraph.flowchart.data` | `[/"…"/]` parallelogram |
| Trapezoid | `shape=trapezoid` | `[/"…"\]` trapezoid |
| Flowchart manual operation | `shape=mxgraph.flowchart.manual_operation` | `[\"…"/]` inverted trapezoid |
| Process, flowchart predefined process | `shape=process`, `shape=mxgraph.flowchart.predefined_process` | `[["…"]]` subroutine |
| Flowchart terminator | `shape=mxgraph.flowchart.terminator` | `(["…"])` stadium |
| Anything else (document, cloud, triangle, step, note, actor, other flowchart and library shapes) | | `["…"]` rectangle |

### Containers

Containers become Mermaid subgraphs, nested to any depth:

| Draw.io element | Style | Result |
|---|---|---|
| Container, swimlane, pool / lane, list | `swimlane` | subgraph titled with the container's label |
| Group (Arrange > Group) | `group` | subgraph with a blank title |
| Any shape with the Container property set | `container=1` | subgraph titled with the shape's label |

A container with nothing inside it is emitted as an ordinary shape.

### Edges

| Draw.io edge style | Mermaid |
|---|---|
| Solid / dashed or dotted (`dashed=1`) | `-->` / `-.->` |
| Thick (`strokeWidth` 3 or more) | `==>` (dashed lines stay dashed; Mermaid has no thick dashed line) |
| No arrowhead (`endArrow=none`) | `---`, `-.-`, `===` |
| Circle or cross at the end (`endArrow=oval`, `endArrow=cross`) | `--o`, `--x` |
| Same marker at both ends (`startArrow=…`) | `<-->`, `o--o`, `x--x` |
| Arrowhead only at the start | the edge is reversed: `B --> A` |
| Edge labels, including labels added as separate text on the edge | `-->\|"label"\|` |

Different markers at the two ends (e.g. a circle at the start and an arrow at the end) keep only the end marker. Other arrowhead styles (block, open, diamond, ER notation, …) become a normal arrow.

### Labels and IDs

HTML formatting in labels (fonts, colors, bold) is removed, and line breaks are joined with a space. Node IDs are built from labels by default; see `--drawio-ids` above.

### Not supported: shapes with custom properties

Shapes that have custom properties (Edit Data), a link, or a tooltip are stored differently in the Draw.io file (wrapped in `<object>` or `<UserObject>` elements), and **FlowForge skips them**. A warning names each skipped shape, and edges connected to a skipped shape are skipped too. To include such a shape, remove its custom properties, link and tooltip in Draw.io.

Colors, fonts, positions and sizes are not carried over.

---

## API Overview

### `FlowForgeConverter`
- **Constructor Parameters:**
  - `log_level`: Logging level (e.g., `logging.DEBUG`, `logging.INFO`).
  - `strict_mode`: Boolean flag indicating whether conversion errors should raise exceptions (`True`) or be logged and skipped (`False`).

- **Key Methods:**
  - `load_file(file_path)`: Reads a Draw.io file and returns its content as a string.
  - `list_diagram_pages(xml_data)`: Extracts available diagram pages from the input XML and returns their indices.
  - `convert(input_data, diagram_index=0, direction="TD", diagram_type="flowchart")`: Main conversion method to generate Mermaid code from the specified diagram page.

- **Internal Workflow:**
  1. **Decompression & Multi-Page Extraction:**  
     Detects and decompresses base64/deflate data if necessary.
  2. **XML Parsing:**  
     Uses `xml.etree.ElementTree` to parse the XML.
  3. **Diagram Building:**  
     Builds an internal representation of nodes, edges, and groups.
  4. **Mermaid Emission:**  
     Formats nodes and edges (with recursive subgraph handling) into valid Mermaid syntax.

For detailed documentation on each method, please refer to the inline code documentation in [flowforge.py](flowforge.py).

---

## Logging & Configuration

FlowForge uses Python’s built-in `logging` module. Set the desired logging level in the constructor. In strict mode (`strict_mode=True`), conversion errors will cause the process to halt; in relaxed mode, errors are logged as warnings and the process continues.

Example:

```python
converter = FlowForgeConverter(log_level=logging.DEBUG, strict_mode=False)
```

---

## License

This project is released under the **MIT License**.  
**Attribution is required to Genkins Forge LLC.**  
Please see the [LICENSE](LICENSE) file for the full license text.

---

## Contributing

Contributions are welcome! Please fork the repository and open a pull request with your improvements or bug fixes. For major changes, please open an issue first to discuss your ideas.

When contributing, please ensure:
- Code follows the PEP 8 style guide.
- New features include appropriate tests and documentation.
- All contributions include attribution to **Genkins Forge LLC**.

---

## Credits

Developed and maintained by **Genkins Forge LLC**.  
For further inquiries or support, please contact [info@genkinsforge.com](mailto:info@genkinsforge.com).

---

*Enjoy converting your Draw.io diagrams to Mermaid with FlowForge!*

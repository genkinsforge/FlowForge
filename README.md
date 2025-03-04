# FlowForge

**FlowForge** is a robust and extensible Python framework for converting Draw.io (Diagram.net) diagrams to Mermaid diagrams. This library supports multi-page diagrams, enhanced style parsing, recursive group/subgraph handling, and configurable logging with error correction modes.

> **Note:** This project is released under the [MIT License](LICENSE) with the requirement that credit is given to **Genkins Forge LLC**.

[GitHub Repository](https://github.com/genkinsforge/FlowForge)

---

## Table of Contents

- [Features](#features)
- [Installation](#installation)
- [Usage](#usage)
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

Clone the repository:

```bash
git clone https://github.com/genkinsforge/FlowForge.git
cd FlowForge
```

Install the required dependencies (if any):

```bash
pip install -r requirements.txt
```

> **Note:** FlowForge is built using Python’s standard library modules, so external dependencies are minimal.

---

## Usage

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

## API Overview

### FlowForgeConverter

**Constructor Parameters:**

- `log_level`: Logging level (e.g., `logging.DEBUG`, `logging.INFO`).
- `strict_mode`: Boolean flag indicating whether conversion errors should raise exceptions (`True`) or be logged and skipped (`False`).

**Key Methods:**

- `load_file(file_path)`: Reads a Draw.io file and returns its content as a string.
- `list_diagram_pages(xml_data)`: Extracts available diagram pages from the input XML and returns their indices.
- `convert(input_data, diagram_index=0, direction="TD", diagram_type="flowchart")`: Main conversion method to generate Mermaid code from the specified diagram page.

**Internal Workflow:**

1. **Decompression & Multi-Page Extraction:**  
   Detects and decompresses base64/deflate data if necessary.
2. **XML Parsing:**  
   Uses `xml.etree.ElementTree` to parse the XML.
3. **Diagram Building:**  
   Builds an internal representation of nodes, edges, and groups.
4. **Mermaid Emission:**  
   Formats nodes and edges (with recursive subgraph handling) into valid Mermaid syntax.

For detailed documentation on each method, please refer to the inline code documentation in `flowforge.py`.

---

## Logging & Configuration

FlowForge uses Python’s built-in `logging` module. Set the desired logging level in the constructor. In strict mode (`strict_mode=True`), conversion errors will cause the process to halt; in relaxed mode, errors are logged as warnings and the process continues.

**Example:**

```python
converter = FlowForgeConverter(log_level=logging.DEBUG, strict_mode=False)
```

---

## License

This project is released under the MIT License.  
Attribution is required to **Genkins Forge LLC**.  
Please see the [LICENSE](LICENSE) file for the full license text.

---

## Contributing

Contributions are welcome! Please fork the repository and open a pull request with your improvements or bug fixes. For major changes, please open an issue first to discuss your ideas.

When contributing, please ensure:

- Code follows the [PEP 8](https://peps.python.org/pep-0008/) style guide.
- New features include appropriate tests and documentation.
- All contributions include attribution to **Genkins Forge LLC**.

---

## Credits

Developed and maintained by **Genkins Forge LLC**.  
For further inquiries or support, please contact [info@genkinsforge.com](mailto:info@genkinsforge.com).

---

Enjoy converting your Draw.io diagrams to Mermaid with **FlowForge**!

---

With these updates, both your code and README are aligned under the new **FlowForge** branding. You can now proceed to create your GitHub repository at [https://github.com/genkinsforge/FlowForge](https://github.com/genkinsforge/FlowForge) and continue to expand the library with additional features.

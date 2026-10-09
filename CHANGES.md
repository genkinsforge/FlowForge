# Changes

This document describes how this fork of FlowForge differs from the original Genkins Forge release. All changes are on the `srs-main` branch and date from October 2026.

The changes fall into five areas:

- a command-line runner that writes Mermaid diagrams to Markdown files
- readable node IDs
- fixes that make the Mermaid output valid
- fixes that keep diagram content from being lost or duplicated
- wider support for Draw.io shapes, containers and edge styles, with warnings when something can't be converted exactly

## Terms used in this document

A **shape** is an element in a Draw.io diagram, such as a rectangle or a diamond. A **node** is the shape's counterpart in the Mermaid output. An **edge** is a line that connects two shapes, with or without arrowheads. A **container** is a Draw.io shape that holds other shapes; swimlanes and groups are both containers. A **subgraph** is the Mermaid structure that FlowForge produces from a container.

## Command-line runner

FlowForge now includes a command-line runner. It reads a Draw.io file and writes a Markdown file that contains the diagram as a Mermaid code block. Before this change, converting a file meant writing a Python script around the library.

To convert a file, run `python -m flowforge` followed by the file name. After you install FlowForge with pip, the shorter `flowforge` command does the same thing. If the file name has no extension, the runner adds `.drawio`. For example, `flowforge design/issues` reads `design/issues.drawio` and writes `design/issues.md`.

The runner converts every page in the Draw.io file. Each page gets its own Mermaid block, under a heading with the page's name. A single-page file produces one Mermaid block with no page heading.

The runner overwrites an existing output file without asking. If the default output name would replace a file you want to keep, use the `-o` option to choose another name.

The runner accepts these options:

- `-o` sets the output file name.
- `--index` converts only one page, numbered from zero.
- `--direction` sets the Mermaid flow direction, such as `TD` for top-down or `LR` for left-to-right. The default is `TD`.
- `--drawio-ids` uses Draw.io's own cell IDs as node IDs. See the next section.
- `--strict` stops at the first conversion error. Without it, FlowForge skips what it can't convert and carries on.
- `-v` prints detailed progress, including each shape and edge counted in a simplification summary.

The runner reports a missing input file, an empty diagram, or a page number out of range as an error, and exits with a nonzero status.

## Readable node IDs

FlowForge now builds each node ID from the shape's label, so a shape labelled "Capacity List" becomes the node `capacity_list`. Draw.io's own cell IDs are random strings, such as `65PPJ_XJzwb0lOGMphRH-12`, which are hard to read and hard to refer to.

When several shapes share a label, FlowForge puts the ID of the enclosing container in front. A "Capacity List" shape inside the "Law" swimlane becomes `law_capacity_list`. If two IDs are still identical, FlowForge numbers them in the order the shapes appear in the file, such as `social_stance_list_stance_1` and `social_stance_list_stance_2`.

FlowForge also adjusts IDs that Mermaid can't accept:

- A label that is a Mermaid keyword gets a suffix, so "end" becomes `end_node`.
- A label that starts with a digit gets a prefix, so "2nd stage" becomes `n_2nd_stage`.
- Accented letters lose their accents, so "Café" becomes `cafe`.
- FlowForge cuts IDs longer than 40 characters at a word boundary.

Readable IDs are the default. To use Draw.io's cell IDs instead, pass `--drawio-ids` to the runner, or pass `readable_ids=False` to the `convert` method in Python.

Numbered IDs depend on the order of shapes in the file. Adding or deleting a shape with a repeated label can renumber the shapes after it. Giving shapes distinct labels avoids this.

## Valid Mermaid output

The original converter produced Mermaid that some viewers rejected as a syntax error. FlowForge now produces valid Mermaid in each of the cases below, and Mermaid's own parser accepts the output.

**HTML in labels.** Draw.io stores formatted labels as HTML. A label with a font color, for example, contains a `<font color="…">` tag. The quotation marks inside those tags ended the Mermaid label early. FlowForge now removes formatting tags and keeps only the label text. It also joins multi-line labels into one line, so "Vote" on one line and "Pass" on the next becomes "Vote Pass".

**Special characters in labels.** A quotation mark typed into a label also broke the Mermaid syntax. FlowForge now replaces quotation marks, angle brackets and the `#` sign with Mermaid's escape codes, so they display correctly.

**Circles.** The converter wrote circle nodes with spaces inside the brackets, which Mermaid rejects. Any diagram containing an ellipse failed to render.

**Labelled dashed edges.** The converter wrote a labelled dashed edge in a form Mermaid doesn't accept. FlowForge now writes every edge label in Mermaid's pipe form, which works with all line styles.

**Lines without arrowheads.** A solid edge with no arrowhead came out as two dashes, which Mermaid rejects. It now comes out as three dashes, Mermaid's plain line.

**Subgraph titles.** Container titles now appear in quotation marks, so titles with spaces or punctuation display correctly.

## Content that was lost or duplicated

**Edge labels.** In Draw.io, text added to an edge is usually stored as a separate small shape attached to that edge. The converter treated each of these as a standalone node, so labels such as "yes" or "Propose" appeared as loose boxes instead of on their edges. FlowForge now moves the text onto the edge. When an edge has more than one piece of text, FlowForge joins them with a space.

**Containers shown twice.** The converter wrote each container twice, once as a subgraph and again as an ordinary node. It also wrote a nested container a second time at the top level of the diagram. FlowForge now writes each container once, in its correct place.

**Edges to containers.** An edge pointing at a container used a different ID from the container's subgraph. Mermaid drew the edge to a stray extra node instead of the container. Edges now connect to the subgraph itself.

**Diamonds.** Draw.io marks a diamond in several ways. The converter recognized only one of them, so diamonds from Draw.io's standard palettes came out as rectangles. FlowForge now recognizes the plain diamond style and the flowchart library's decision shape.

**Dashed lines.** A Draw.io style of `dashed=0` explicitly means a solid line. The converter treated any `dashed` setting as dashed. It now treats `dashed=0` as solid.

**Multi-page files.** The converter read only the first page of a multi-page file saved in Draw.io's uncompressed format, which is the default in current versions of Draw.io. FlowForge now reads every page.

**Compressed pages.** Draw.io can save pages in a compressed format. The converter couldn't read any page saved that way, because it didn't reverse an encoding step that Draw.io applies before compressing. FlowForge now reads compressed pages.

## Shapes, containers and edges

FlowForge now maps many more Draw.io elements to Mermaid. The README's "Supported Draw.io Elements" section lists every mapping. This section summarizes what changed.

**Shapes.** The original converter produced four Mermaid node shapes: rectangle, rounded rectangle, circle and diamond. FlowForge now also produces the hexagon, cylinder, parallelogram, trapezoid, subroutine box, stadium and double circle shapes. The new mappings cover the matching Draw.io shapes, including the flowchart library's database, data, predefined process, terminator and preparation shapes.

Draw.io's cloud and double ellipse shapes were previously drawn as circles. A double ellipse now becomes a double circle. A cloud becomes a rectangle, because Mermaid's classic syntax has no cloud shape. Other shapes with no Mermaid equivalent, such as document, note, actor and triangle, also become rectangles. FlowForge keeps their labels and connections.

**Containers.** Swimlanes, which the Draw.io editor offers as its "Container" shape, already became subgraphs. Groups made with Arrange > Group also became subgraphs, but with a placeholder title built from the group's cell ID, such as `Group_gr`. They now have a blank title. Any shape with Draw.io's container property set now becomes a subgraph as well; before, its contents came out as unconnected nodes.

**Edges.** The original converter kept only two edge properties: solid or dashed, and arrowhead or none. FlowForge now also reproduces:

- thick lines, drawn as Mermaid's thick line
- circle and cross arrowheads
- matching markers at both ends of an edge
- an arrowhead at the start only, which FlowForge draws by reversing the edge

## Warnings

FlowForge now warns you when it skips or simplifies part of a diagram. Before, it did both silently.

**Skipped shapes.** FlowForge doesn't convert shapes that have custom properties (added with Draw.io's Edit Data command), a link, or a tooltip. Draw.io stores these shapes in a different form, and FlowForge skips them. FlowForge now names each skipped shape in a warning. When FlowForge skips an edge because it connects to a skipped shape, the warning says so. To include such a shape, remove its custom properties, link and tooltip in Draw.io.

**Simplified shapes and edges.** Some Draw.io features have no Mermaid equivalent. FlowForge simplifies these and counts each simplified shape or edge:

- a shape with no Mermaid equivalent, drawn as a rectangle
- an unusual arrowhead, such as a diamond or entity-relationship notation, drawn as a normal arrow
- different markers at the two ends of an edge; FlowForge keeps only the end marker
- a thick dashed line, drawn as a normal dashed line

After converting each page, FlowForge prints a single summary line, such as "2 edges and 3 shapes were simplified to fit Mermaid." Use the runner's `-v` option to list each simplified shape and edge, with the reason. FlowForge counts a shape or edge once, even when it was simplified in more than one way.

## Changes to existing output

If you have Markdown files from the original converter, regenerating them will produce different output:

- Node IDs come from labels unless you pass `--drawio-ids`.
- With `--drawio-ids`, container IDs now start with `N`, matching every other node ID.
- Labels are single lines with formatting removed.
- Edge labels use Mermaid's pipe form.

The diagrams these files describe are unchanged, apart from the corrections listed above.

## Known limitations

- FlowForge skips shapes with custom properties, links or tooltips. See the Warnings section.
- FlowForge doesn't carry colors, fonts, positions or sizes into the Mermaid output.
- FlowForge produces Mermaid flowcharts only.

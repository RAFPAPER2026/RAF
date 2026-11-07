### Deliverable Inspection Protocol

For each deliverable type, use the corresponding inspection method to ensure that you not only see that the file exists but also verify that its content/layout/interaction meets the requirements.

#### PPT / .pptx

- You must use the `pptx` skill to render the slides as images and then inspect the layout and visual effects; judging from text extraction alone is not allowed.
- Recommended workflow: call the `pptx` skill's `scripts/thumbnail.py` to render the `.pptx` into page-by-page images, and inspect the layout, text and chart placement, color scheme, and readability of each page one by one.
- If you need to extract text for content verification, you may use the `markitdown` tool in the `pptx` skill to extract text, but layout judgments must still be based on the rendered images.

#### HTML / .html

- You must use the `webapp-testing` skill (based on Playwright) to open the local HTML file in a browser (use a temporary lightweight static server to host the page and enable dynamic online loading), and judge based on interactions and screenshots; judging from the page source code alone is not allowed. If a CDN or a similar reason causes a chart or other page element to fail to render, this should not be classified as a visual defect; when scoring, mark the relevant rubric leaf as passed, explain the actual circumstances in the justification, and report the anomaly truthfully in `exceptions.md`.
- Recommended workflow: start a browser with the `webapp-testing` skill → open the HTML file in the result directory → try each key interaction (click, input, hover, etc.) item by item → capture screenshots of the visual states → judge whether the page meets the requirements based on the screenshots, interaction results, and page source code together.

#### PDF / .pdf

- Use the `pdf` skill to read/extract PDF content; if layout verification is needed, render it as images and inspect them.

#### DOCX / .docx

- Use the `docx` skill to extract text and structure; if layout verification is needed, render it as images and inspect them.

#### XLSX / .xlsx

- Use the `xlsx` skill to extract cell data, formulas, and charts; if layout verification is needed, render it as images and inspect them.

#### Other file types

- Text/code/JSON files can be inspected directly with `Read`.
- Images can be inspected directly with `Read`.

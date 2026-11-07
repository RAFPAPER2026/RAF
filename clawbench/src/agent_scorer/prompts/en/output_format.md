### Output Format

Your output must be in JSON format and contain the following fields:

- **rubric_results**: An object whose keys are the leaf-node IDs (marked in square brackets in the rubric tree, in the form `[node-xxxxxxxxxxxx]`), and whose values are objects:
  - `passed`: A Boolean value; true = passed, false = failed
  - `reasoning`: A string explaining the specific basis for your judgment (1-2 sentences, citing evidence)
  - You must cover all leaf nodes

- **confidence**: Your confidence in the overall evaluation result, between 0.0 and 1.0
  - 1.0 = Very confident; the evidence is sufficient and unambiguous
  - 0.7 = Fairly confident; the main judgments are supported, but some details are uncertain
  - 0.4 = Moderate; the evidence is limited or contradictory
  - 0.0 = Completely uncertain; a reliable judgment cannot be made

- **time_analysis**: A required string. An **item-by-item record made during the scoring process** of the time-window analysis: record the time analysis immediately when a time-related leaf is scored; do not fill it in after the fact. It must include:
  - The execution date (UTC+8, the authoritative baseline, taken from the user prompt's metadata section)
  - Each time-related leaf-node ID and its required absolute time window
  - The dates actually used/produced by the agent
  - The per-item satisfied/unsatisfied conclusion
  - If the task has no time requirement at all, writing "No time-window requirement" is sufficient for this field

- **info_fidelity_analysis**: A required string. An **item-by-item record made during the scoring process** of the search-information extraction analysis: record it immediately when a search-related leaf is scored; do not fill it in after the fact. It must include:
  - Each search-related leaf-node ID and the information it requires (the part that must be obtained from search/browsing results)
  - The corresponding search/browsing tool calls and a summary of the returned content
  - The corresponding content in the agent's deliverable
  - The per-item faithful/unfaithful conclusion (fabrication/misuse/substitution/misrepresentation)
  - If the task does not involve obtaining external information through search/browsing at all, writing "No search-information fidelity requirement" is sufficient for this field

- **needs_human_review**: A required Boolean value, filled in according to the **anomaly and uncertainty assessment** part of the evaluation workflow.

- **review_notes**: A required string (non-empty). Explanation of the uncertainty: when `needs_human_review=true`, specify the matched condition and its basis; when `needs_human_review=false`, write "No human review required".

Note: The structured-output JSON Schema defines the field structure. If the descriptions above conflict with the Schema, the Schema takes precedence.

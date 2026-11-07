### Critical Rules

#### Scoring Principles

- Your judgments must be based on `sessions.json` and the **concrete deliverables** in `workspace/`, not on assumptions.
- You **only need to judge the leaf nodes**; the results of AND/OR groups are derived automatically.
- If the agent's output is partially correct, truthfully judge the pass/fail of each leaf node.
- You must cover all leaf nodes; an omitted node will be treated as failed.

#### Criteria for Special Cases

- If the task involves obtaining external information through search/browsing, strictly follow the **Search-Information Fidelity Criterion** section below to determine whether the agent correctly extracted and faithfully used the information from the search results, without fabrication/misuse/hallucination/substitution.
- If a rubric leaf assumes a certain circumstance, handle it as follows:
  - If the leaf node is in an OR group or the assumed circumstance is a necessary part of completing the task, judge whether it passes according to the actual situation; do not apply the two presumptions below.
  - If the assumed circumstance is not necessary for completing the task and **indeed** did not occur during the actual execution (the trajectory or workspace clearly confirms that the premise did not occur), mark it as passed, and explain in `reasoning` that the assumed circumstance was not involved and does not affect task completion, so it is presumed passed.
  - If it is **impossible to determine** whether the leaf node's assumed circumstance was triggered, or the evidence is insufficient to judge whether it was achieved, mark it as failed, and explain the insufficient evidence in `reasoning`.
- If the task involves "latest", "previous N days", "next week N", or other time-reasoning and explicit recency/time-window requirements, strictly follow the **Time-Window Criterion** section below.

#### Time-Window Criterion (Mandatory Protocol)

Time-related expressions:
- **Relative time**: `latest` / `most recent N days` / `the past week` / `N days before` / `past N days` / `previous N days` / `next N days` / `future N days` / `next week N` / `this week` / `this month` / `last month` / `this year`, etc.
- **Absolute time**: a specified date or a specified date range (e.g., "July 1 – July 3").

For every leaf node involving the above expressions (whether a completion leaf or a quality leaf), **you must** complete the following steps before setting `passed`:

1. **Anchor the execution date**: Take the execution date from the "## Execution Trace Metadata" section of the user prompt (UTC+8, the authoritative baseline). **Do not** use the agent's self-reported "today", the current evaluation time, or dates appearing in tool returns as the baseline.
2. **Convert to an absolute window**: Convert the time-related requirement into an absolute date interval according to the direction convention. You must use the Linux system's built-in `date` tool or a Python script for the conversion; do not reason it out yourself, to prevent time-reasoning errors.
   - `previous/prior/past` = earlier than the execution date; `after/future/next` = later than the execution date.
   - Example (execution date = 2026-07-04):
     - `the past week` = [2026-06-27, 2026-07-04]
     - `the next 3 days` = [2026-07-04, 2026-07-07]
     - `the previous three days` = [2026-07-01, 2026-07-03]
3. **Find the agent's actual dates**: Locate the dates the agent actually used/produced from tool-call keywords, date fragments in fetched URLs (e.g., `t20250414`, `depdate=2026-07-05`), and the deliverable body.
4. **Compare and decide**: The requirement is satisfied only if the actual dates in the agent's deliverable **fully cover** the required window; if the deliverable does not fully cover the window, mark the relevant leaf **as failed immediately**, with `reasoning` stating "Time window not satisfied: required [window], agent actual [actual dates]".
5. **Do not reinterpret**: Time-window satisfaction is a hard gate for both **completion leaves** and **quality leaves**; even if the agent retrieved/summarized content, as long as the dates do not match, the relevant leaves are all marked failed, and the impact must not be reinterpreted or weakened.
6. **Insufficient evidence**: If the agent's actual dates cannot be confirmed, apply the existing "insufficient evidence" rule and mark as failed, with `reasoning` noting "Unable to confirm whether the time window was satisfied".
7. **Write to `time_analysis`**: During leaf-by-leaf scoring, write the above analysis (execution date, IDs of time-related leaves and their required windows, the agent's actual dates, and per-item satisfied/unsatisfied conclusions) into the `time_analysis` field; if there is no time requirement, write "No time-window requirement".

#### Search-Information Fidelity Criterion (Mandatory Protocol)

Applicability: This protocol applies mandatorily when the task requires the agent to obtain external information through search/browsing tools (such as `web_search`, `web_fetch`, `browse`, `browser`, etc.) and use the obtained information in a deliverable. Information sources include but are not limited to: web search results, fetched webpage text, and fields obtained through search/browsing in structured API responses.

For every leaf node whose required information comes from search/browsing results (whether a completion leaf or a quality leaf), **you must** complete the following steps before setting `passed`:

1. **Identify search-dependent leaves**: Determine leaf by leaf whether the information required by the leaf must be obtained from search/browsing results (the information cannot be derived solely from task input files or the agent's internal knowledge and must rely on external retrieval). List the IDs of all search-dependent leaves.
2. **Locate the returned search content**: Find the search/browsing tool calls in the tool-call sequence of the "## Execution Trace Metadata" section of the user prompt (tool calls with a `query` line, including direct search tools such as `web_search`/`web_fetch`/`browser`, as well as indirect search calls that invoke search-type skill scripts through `exec`), and inspect the corresponding raw tool returns in `sessions.json` (search-result snippets, fetched webpage text, API responses, etc.). **Only the content actually returned by the tools** is trusted as the comparison baseline; do not use the agent's self-statements or later paraphrases.
3. **Compare the deliverable with the returned content**: Compare the information in the agent's final deliverable corresponding to the search-dependent leaves with the search returns located in Step 2, item by item, checking for any of the following:
   - **Fabrication/hallucination**: Information appears in the deliverable that does not exist in the search returns (invented ratings, numbers, names, dates, etc.).
   - **Misuse/mismatching**: Content returned by the search is applied to the wrong object (e.g., assigning movie A's rating to movie B), misattribution, or field misalignment.
   - **Substitution/tampering**: Information that should come from the search results is replaced with content from a non-search source, or old/irrelevant data is substituted without a new search.
   - **Misrepresentation through selective extraction**: Extracting fragments of the search returns in a way that changes their original meaning, making them inconsistent with the information required by the use case.
4. **Decide and mark**: If any of the above is found, immediately mark the relevant search-dependent leaf **as failed**, with `reasoning` stating "Unfaithful search-information extraction: required [required information], search returned [actual returned content], agent delivered [delivered content], issue: [fabrication/misuse/substitution/misrepresentation]".
5. **Do not reinterpret (hard gate)**: Faithful extraction and use of search information is a hard gate for both **completion leaves** and **quality leaves**; even if the deliverable formally satisfies the leaf wording (e.g., format, item count, complete fields), as long as fabrication/misuse/hallucination/substitution exists, the relevant leaves are all marked failed, and the impact must not be reinterpreted or weakened.
6. **Insufficient evidence**: If the search returns cannot be confirmed (e.g., a tool call failed, the return was empty, or the corresponding record is missing from `sessions.json`), apply the existing "insufficient evidence" rule and mark as failed, with `reasoning` noting "Unable to confirm whether search information was faithfully extracted". This item addresses "unverifiable", which is distinct from "confirmed unfaithful" in Step 4.
7. **Write to `info_fidelity_analysis`**: During leaf-by-leaf scoring, record the above analysis immediately (do not fill it in after the fact) in the `info_fidelity_analysis` field; it must include: the IDs of search-dependent leaves and their required information, the corresponding search tool calls and summaries of the returned content, the content delivered by the agent, and per-item faithful/unfaithful conclusions. When the task does not involve obtaining external information through search/browsing at all, write "No search-information fidelity requirement".

#### Output Requirements

- Each leaf node's reasoning should cite the **concrete facts** you observed (e.g., "The agent successfully created a calendar event in the third conversation round"), not generic statements.
- `confidence` reflects **your overall confidence in the evaluation result**, not the task completion quality.
- Each leaf node ID is marked in square brackets in the rubric tree (e.g., `[node-xxxxxxxxxxxx]`); use these IDs as keys when outputting `rubric_results`.

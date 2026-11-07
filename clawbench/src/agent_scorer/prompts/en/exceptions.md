### Handling Anomalies and Anomalous Deliverables

When any of the following abnormal situations occurs, handle it according to the rules in this section, and truthfully describe the anomaly encountered in the `reasoning` of the corresponding leaf node.

#### Set the review flag in the structured output when a review condition is met

This section deals with "how to score anomalous deliverables". The review flag is only an additional prompt for human review and does not change the `passed` conclusion.

#### Deliverable not visible / not found

- If the deliverable file required by the task is not found in `workspace/`, mark the relevant leaf node as failed, and note "Deliverable not found: <filename/type>" in `reasoning`.
- If the deliverable exists but the filename is empty or the size is 0, treat it as not delivered.

#### Deliverable unreadable / corrupted

- If the deliverable file exists but cannot be opened/parsed (e.g., a corrupted .pptx, an HTML page that cannot load, a corrupted PDF), mark the relevant leaf node as failed, and note "Deliverable unreadable: <reason>" in `reasoning`.
- Do not give up the entire evaluation because an inspection tool call fails; continue evaluating the remaining leaf nodes.

#### Special deliverables not in the result directory's workspace/

- If the deliverable required by the task is not a conventional file — for example, it requires writing to a device's notes or creating a calendar event, with no actual entity in the file system — determine the content based on the tool-call parameters in the execution trajectory, and determine whether the delivery succeeded based on the tool-call result (a successful tool call counts as successful delivery; otherwise it counts as failed delivery; evaluate delivery quality from the tool-call parameters).

#### Missing sessions.json or workspace

- If `sessions.json` is missing: the execution trajectory cannot be verified; judge only from the outputs in `workspace/`, note in `reasoning` that the trajectory is unavailable, and lower `confidence` accordingly.
- If `workspace/` is missing or empty: mark all leaf nodes that depend on workspace outputs as failed, and note "workspace is empty or missing" in `reasoning`.

#### Missing task input files

- If an input file mentioned in the task query does not exist under `init_env/` in the task directory, first reconstruct the input the agent actually received from its execution trajectory (tool-call parameters and files read in the trajectory may serve as evidence), and continue the evaluation; do not mark the leaf as failed directly just because the input file is missing.

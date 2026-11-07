# Third-party notices

This repository contains two kinds of material:

1. **Code and annotations authored by the RAF/ClawBench authors**, released under
   Apache-2.0 (code) and CC BY 4.0 (benchmark data, annotations, prompt assets).
2. **Task fixtures** under `clawbench/tasks/*/init_env/`. These files are the initial
   environments of the benchmark tasks. They include fictional/synthesized documents,
   spreadsheets, calendars, images, and in some cases publicly available documents
   (for example arXiv papers or public reports) that were used as task inputs.

The CC BY 4.0 license covers the task definitions, rubrics, metadata and other
material authored for this release. Third-party files contained in `init_env/`
remain under the copyright and license terms of their original authors; they are
included as benchmark fixtures only. If you redistribute the benchmark, keep this
notice and verify that the third-party content is acceptable for your use case.

The OpenClaw sandbox image referenced by `clawbench/docker/openclaw/` is derived from
the public `ghcr.io/openclaw/openclaw` image and is **not** redistributed in this
repository. Refer to the upstream project for its license and terms.

If you believe a file should not be redistributed, please open an issue in the
repository and we will address it.

## Referenced public projects

Some ClawBench task scenarios were inspired by, or adapted from, publicly available
agent-evaluation projects:

- Claw-Eval: <https://github.com/claw-eval/claw-eval>
- PinchBench: <https://github.com/pinchbench/skill>

Their code and data are not redistributed in this repository; the references are for
attribution of task-design inspiration.

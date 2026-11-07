---
dataset_info:
  features:
  - name: image
    dtype: image
  - name: conversation
    dtype: string
  - name: category
    dtype: string
  splits:
  - name: eval
    num_bytes: 36977825.0
    num_examples: 92
  download_size: 36774506
  dataset_size: 36977825.0
configs:
- config_name: default
  data_files:
  - split: eval
    path: data/eval-*
---

# MM-MT-Bench

MM-MT-Bench is a multi-turn LLM-as-a-judge evaluation benchmark similar to the text MT-Bench for testing multimodal instruction-tuned models. While existing benchmarks like MMMU, MathVista, ChartQA and so on are focused on closed-ended questions with short responses, they do not evaluate model's ability to follow user instructions in multi-turn dialogues and answer open-ended questions in a zero-shot manner. MM MT-Bench is designed to overcome this limitation. The [mistral-evals](https://github.com/mistralai/mistral-evals) repository provides an example script on how to evaluate a model on this benchmark.

[Paper link](https://arxiv.org/abs/2410.07073)
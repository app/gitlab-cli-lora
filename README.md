# gitlab-cli-lora

A LoRA fine-tune of a local model, done end to end on one 24 GiB GPU — a frozen
benchmark, SFT datasets, Unsloth QLoRA training, vLLM evaluation, and a GGUF
adapter for llama.cpp.

Qwen3.8-27B on an RTX 5090 D v2, driven through OpenCode, did not know the
GitLab CLI — `glab` calls failed. The fix lives here.

This project is for your agent. Show it the repository and it will train the
adapter on your local GPU — the [agent guide](AGENTS.md) tells it what to do.
One caveat: it downloads about 60 GB of model weights and tooling.

No agent yet? Run one of these in the project directory:

- [Container image with the agent, Python toolchain](https://github.com/app/opencode-python)
- [Container image with the agent, TypeScript toolchain](https://github.com/app/opencode-typescript)

# gitlab-cli-lora

A LoRA fine-tune of a local model, end to end on one 24 GiB GPU.

It started from a gap: the best local model of its time (Qwen3.8-27B on an
RTX 5090 D v2), driven through OpenCode, did not know the GitLab CLI — `glab`
calls failed. The fix lives here: a frozen text-only benchmark, SFT datasets
for both serving contracts, Unsloth QLoRA training on that same GPU, vLLM
evaluation, and a GGUF adapter handed off to a local llama.cpp stack.

This project is for your agent. Just show it the repository — the
[agent guide](AGENTS.md) tells it what to do.

No agent yet? Run one of these in the project directory:

- [Container image with the agent, Python toolchain](https://github.com/app/opencode-python)
- [Container image with the agent, TypeScript toolchain](https://github.com/app/opencode-typescript)

# gitlab-cli-lora

A LoRA fine-tune of a local model, end to end on one 24 GiB GPU.

It started from a gap: the best local model of its time (Qwen3.8-27B on an
RTX 5090 D v2), driven through OpenCode, did not know the GitLab CLI — `glab`
calls failed. The fix lives here: a frozen text-only benchmark, SFT datasets
for both serving contracts, Unsloth QLoRA training on that same GPU, vLLM
evaluation, and a GGUF adapter handed off to a local llama.cpp stack.

The pipeline is long, stateful and full of frozen artifacts that must not be
touched by hand. Hand the repository to a coding agent and ask it to take
over: the [agent guide](AGENTS.md) is the operating manual for the whole loop.

Everything here ran inside [OpenCode](https://opencode.ai) in a container —
one run command from the project directory, nothing to install:

- [Container image, Python toolchain](https://github.com/app/opencode-python)
- [Container image, TypeScript toolchain](https://github.com/app/opencode-typescript)

# gitlab-cli-lora

A LoRA fine-tune of a local model, end to end on one 24 GiB GPU.

It started from a gap: the best local model of its time (Qwen3.8-27B on an
RTX 5090 D v2), driven through OpenCode, did not know the GitLab CLI — `glab`
calls failed. The fix lives here: a frozen text-only benchmark, SFT datasets
for both serving contracts, Unsloth QLoRA training on that same GPU, vLLM
evaluation, and a GGUF adapter handed off to a local llama.cpp stack.

This is an agent's project, not a human's. The pipeline is long, stateful and
full of frozen artifacts that must not be touched; hand the repository to a
coding agent and ask it to take over. Start at the
[agent guide](AGENTS.md), the operating manual for the whole loop.

No agent yet? Everything above was driven by [OpenCode](https://opencode.ai)
inside a container: one run command, nothing to install. Pass the GPU device
flags listed in the [agent guide](AGENTS.md) and the agent trains the adapter
on your own 24 GiB GPU.

- [Container image with the agent, Python toolchain](https://github.com/app/opencode-python)
- [Container image with the agent, TypeScript toolchain](https://github.com/app/opencode-typescript)

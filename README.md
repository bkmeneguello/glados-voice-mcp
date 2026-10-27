# glados-voice-mcp

A warm, shared GLaDOS text-to-speech server for agents, exposed as an [MCP](https://modelcontextprotocol.io) tool.
It builds on [nimaid/GLaDOS-TTS](https://github.com/nimaid/GLaDOS-TTS), included unmodified as a git submodule.

> **Using an AI agent?** Point it at this repository and ask it to follow [`AGENTS.md`](AGENTS.md); it contains every step to install, register and verify the server.

- **Fast:** about 100 ms to first audio once the models are loaded; text is split into sentences and the first one plays while the rest is still being synthesized.
- **Lazy and shared:** the MCP process is a thin proxy. The first `speak` starts one shared daemon (`127.0.0.1:18765`) that loads the models, serves every agent on one audio device, and exits after 10 minutes without requests or speech.
- **In character:** the persona is part of the tool description and `speak` rejects calls with `in_character=false`. The server cannot verify the style of the text itself.
- **One voice at a time:** if a message is loading or playing, `speak` returns `BUSY ... Retry in about N seconds` so agents never talk over each other. `stop` cuts speech for everyone.

## Install

No clone or project directory is needed: [uv](https://docs.astral.sh/uv/) installs straight from this repository (including the submodule). Pick exactly one onnxruntime extra: `cpu` or `cuda` (NVIDIA, CUDA 13 wheels). Replace `https://github.com/bkmeneguello/glados-voice-mcp` with this repository's URL.

```bash
# 1. Build the environment and download the models once (about 125 MB, stored in your user data dir)
uvx --from "glados-voice-mcp[cpu] @ git+https://github.com/bkmeneguello/glados-voice-mcp" glados-voice download-models

# 2. Try it (plays audio)
uvx --from "glados-voice-mcp[cpu] @ git+https://github.com/bkmeneguello/glados-voice-mcp" glados-voice say "Hello, test subject."
```

Prefer a persistent command? `uv tool install "glados-voice-mcp[cpu] @ git+https://github.com/bkmeneguello/glados-voice-mcp"` or `pipx install "..."` puts `glados-voice-mcp` on your `PATH`. To develop, clone with `git clone --recurse-submodules https://github.com/bkmeneguello/glados-voice-mcp` and run `uv pip install ".[cpu]"` in a venv.

## Register the MCP server

```bash
claude mcp add glados-voice -- uvx --from "glados-voice-mcp[cpu] @ git+https://github.com/bkmeneguello/glados-voice-mcp" glados-voice-mcp
```

For other clients use the command `uvx` with the arguments `--from "glados-voice-mcp[cpu] @ git+https://github.com/bkmeneguello/glados-voice-mcp" glados-voice-mcp`; [`AGENTS.md`](AGENTS.md) has Codex, Gemini and JSON examples.

Tools: `speak(text, in_character, wait=false)`, `stop()`, `status()`.

## Configuration (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `GLADOS_IDLE_SECONDS` | `600` | Idle time before the daemon exits and unloads the models |
| `GLADOS_PORT` | `18765` | Localhost port of the shared daemon |
| `GLADOS_BACKEND` | `cpu` | `cpu` (lowest latency for sentences), `cuda`, or `auto` (CPU for short chunks, CUDA for long) |
| `GLADOS_MODELS_DIR` | OS user data dir | Model files, e.g. `%LOCALAPPDATA%\glados-voice\models` on Windows, `~/.local/share/glados-voice/models` on Linux |

The daemon log is `glados_voice_daemon.log` in the system temp directory. The daemon accepts requests from any local process and has no authentication.

## Python use

```python
from glados_voice import VoiceEngine

engine = VoiceEngine().start()   # loads in the background
engine.speak("Hello. This is a test.")
engine.wait_idle()
```

## Credits and license

MIT, see `LICENSE` and `NOTICE.md`. Voice models come from [dnhkng/GlaDOS](https://github.com/dnhkng/GlaDOS) and are downloaded at first use, not stored here.

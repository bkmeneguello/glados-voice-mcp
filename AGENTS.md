# Agent instructions: install and configure glados-voice-mcp

You were pointed at this repository to install and configure its MCP server for the user. Follow these steps in order, run the verification at the end, and report what you did. Ask the user before installing system-level software (uv, git, GPU drivers) or editing configuration outside the user's own MCP client config. **Do not clone this repository for a normal install**: `uvx` installs straight from the repository URL without creating a project directory.

## What this is

An MCP stdio server (`glados-voice-mcp`) that speaks text aloud in GLaDOS's voice. The server process starts instantly. The first `speak` call starts one shared local daemon (`127.0.0.1:18765`) that loads the voice models, serves every agent on one audio device and exits after 10 minutes idle. Needs speakers or an audio output device on the machine where it runs.

Below, `<spec>` is:

```
glados-voice-mcp[cpu] @ git+https://github.com/bkmeneguello/glados-voice-mcp
```

(`[cuda]` instead of `[cpu]` for the GPU, see step 1). To pin a release, append `@<tag>` to the URL.

## Prerequisites

| Need | Check | Notes |
|---|---|---|
| uv | `uv --version` | https://docs.astral.sh/uv/ ; uv downloads Python 3.12 by itself when missing |
| git | `git --version` | uv and pip use it to fetch the repository and its submodule |
| Audio output | n/a | The daemon plays through the default output device |
| Disk space | n/a | About 125 MB of models plus a few hundred MB of packages; the `cuda` extra adds about 1.8 GB (NVIDIA libraries and the GPU runtime) |
| Internet | n/a | github.com and PyPI, for the packages and the first model download |

## 1. Choose the backend extra

Exactly one of `cpu` or `cuda` must be used, never both (the onnxruntime packages conflict).

- Run `nvidia-smi`. If it succeeds and the driver is recent (CUDA 13 capable, roughly driver 580 or newer), use `cuda`. Otherwise use `cpu`.
- Sentence-sized speech is as fast on CPU as on GPU (about 100 ms to first audio once loaded), so `cpu` is a safe default. `cuda` mainly helps with very long texts. If unsure, ask the user.
- macOS has no NVIDIA support: use `cpu`.

## 2. Warm up the cache and download the models (do this first)

The first `uvx` run builds the package (about 15 s) and the first speech needs the models (about 125 MB). Do both now so the MCP client does not time out on its first launch:

```
uvx --from "<spec>" glados-voice download-models
```

Models are verified by SHA-256 and stored in the per-user data directory, shared by every install and surviving upgrades:
- Windows: `%LOCALAPPDATA%\glados-voice\models`
- Linux: `~/.local/share/glados-voice/models`
- macOS: `~/Library/Application Support/glados-voice/models`
- Override with `GLADOS_MODELS_DIR`.

## 3. Register the MCP server with the user's client

The server command is `uvx` with the arguments `--from "<spec>" glados-voice-mcp`. Register only for the clients the user actually uses, and ask which if unclear.

- **Claude Code:** `claude mcp add glados-voice -- uvx --from "<spec>" glados-voice-mcp` (add `--scope user` to make it available in every project).
- **Codex CLI:** add to `~/.codex/config.toml`:
  ```toml
  [mcp_servers.glados-voice]
  command = "uvx"
  args = ["--from", "<spec>", "glados-voice-mcp"]
  ```
- **Gemini CLI or any client using a JSON `mcpServers` map** (for example `~/.gemini/settings.json`, `.mcp.json`):
  ```json
  {
    "mcpServers": {
      "glados-voice": {
        "command": "uvx",
        "args": ["--from", "<spec>", "glados-voice-mcp"]
      }
    }
  }
  ```

If the client cannot find `uvx`, use its absolute path (`where uvx` on Windows, `which uvx` elsewhere).

Optional environment variables for the server entry (`env` in JSON, `[mcp_servers.glados-voice.env]` in TOML):

| Variable | Default | Meaning |
|---|---|---|
| `GLADOS_BACKEND` | `cpu` | `cpu`, `cuda` or `auto` (CPU for short text, CUDA for long). `cuda` and `auto` require the `cuda` extra in `<spec>` |
| `GLADOS_IDLE_SECONDS` | `600` | Idle time before the daemon exits and unloads the models |
| `GLADOS_PORT` | `18765` | Local daemon port; change only on a conflict |
| `GLADOS_MODELS_DIR` | OS user data dir | Where the model files are stored |

Restart or reload the MCP client so it picks up the new server.

### Alternatives to uvx

- **Persistent install** (a command on `PATH`, no re-resolution at each launch): `uv tool install "<spec>"` or `pipx install "<spec>"`, then register the command `glados-voice-mcp` with no arguments. Update with `uv tool upgrade glados-voice-mcp`. If the command is not found, run `uv tool update-shell` (or `pipx ensurepath`) and restart the shell.
- **Development from a clone:** `git clone --recurse-submodules https://github.com/bkmeneguello/glados-voice-mcp`, then `uv venv --python 3.12` and `uv pip install ".[cpu]"` inside it. If the clone has no submodules, run `git submodule update --init --recursive`. Reinstall after source changes.

## 4. Verify

1. Smoke test without MCP (plays audio and prints timings):
   ```
   uvx --from "<spec>" glados-voice say "Hello, test subject."
   ```
   Expect `Ready in ...s ['CPUExecutionProvider']` (or `CUDAExecutionProvider` first for the GPU) and `Time to first audio: ...ms`; the second figure should be roughly 50 to 400 ms. Ask the user whether they heard the voice.
2. In the restarted client, confirm the tools `speak`, `stop` and `status` exist and call `status`. Before the first `speak` it reports `{"running": false}`, which is correct.
3. Call `speak` with `in_character: true` and a short in-character line. The first call returns `queued` after a few seconds and audio starts after the models load (about 5 to 10 seconds the first time). Later calls are fast.

## How agents must use the `speak` tool

- Every message must be written as GLaDOS speaking in the first person, in the persona and delivery rules given in the server instructions, and the call must set `in_character: true` (the default). Otherwise it is rejected.
- Keep messages short (one or two sentences, 25 words at most), plain spoken English: no markdown, code, URLs or emoji.
- Only one message plays at a time across all agents. If the reply starts with `BUSY`, wait the stated number of seconds and retry once or twice; do not poll in a tight loop and do not queue.
- `wait: true` blocks until the speech finishes; the default returns immediately.
- `stop` cuts off speech for every agent; use it sparingly.

## Troubleshooting

- **MCP client times out or shows the server as failed on first start:** the environment was not built yet. Run step 2 once, then reload the client.
- **`git` errors, or `import glados` fails:** the submodule was not fetched. Check `git --version`, retry, or use the clone route with `git submodule update --init --recursive`.
- **`ModuleNotFoundError: onnxruntime`:** the extra is missing from `<spec>`; use `[cpu]` or `[cuda]`.
- **`CUDAExecutionProvider` missing or a CUDA/DLL error:** the spec probably uses `[cpu]`, or the driver is too old. Use `[cuda]`, or fall back to `[cpu]` (do not mix the two in one environment).
- **Model download fails or checksum mismatch:** check internet access and rerun step 2; a bad file is discarded automatically.
- **Silent, but no error:** check the default audio output device; `status` shows whether the daemon is `ready` and `speaking`.
- **Daemon will not start:** read `glados_voice_daemon.log` in the system temp directory (`%TEMP%` on Windows, `$TMPDIR` or `/tmp` elsewhere). A message about the port being unavailable means another process uses it; set `GLADOS_PORT`.
- **After upgrading:** the old daemon keeps running until it idles out; end the `glados_voice.daemon` process to load the new version immediately.

## Security notes

The daemon listens on `127.0.0.1` only but has no authentication, so any local process can make it speak. Do not expose the port to a network. Installing from a git URL runs that repository's build; review or pin a tag (`@<tag>`) for anything you do not control.

## Report back

Tell the user: the backend you chose and why, how you installed it (uvx, uv tool, pipx or clone), which clients you registered the server with (and which files you edited), the output of the verification steps, and whether they heard the voice.

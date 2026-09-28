# Nightly end-to-end smoke test with a local model (rootless Podman, Quadlet)

The end-to-end smoke test (`tests/integration/test_end_to_end_mvp.py`) runs
the whole loop: migrate a fresh database, ingest the ACME fixture notes,
synthesise, compile the wiki and answer a GraphRAG question with citations.

It runs in two places:

| Where | Model | What it proves |
|---|---|---|
| CI, every push (`ci.yml`, job `e2e-smoke`) | `tests/fakes/fake_llm_server.py`, a deterministic OpenAI-compatible stand-in | The data path works end to end. No API key, no cost. |
| Home server, every night (this folder) | A real local model behind llama.cpp / llama-swap on `127.0.0.1:8080` | The same loop gives a sensible answer with a real model. No API key, no cost, nothing leaves the machine. |

Both select `config/llm_routing.selfhosted.yaml` with `EXOCORTEX_LLM_ROUTING`
and send embeddings to the same server through `OPENAI_BASE_URL`.

## Units

| File | What it does |
|---|---|
| `exocortex-e2e-db.container` | Throwaway Postgres (the `exocortex-db` image) on `127.0.0.1:55432`, data in tmpfs. Starts with the test and stops when it ends. |
| `exocortex-e2e.container` | Runs the test once from `ghcr.io/hretheum/exocortex-e2e:main`. Exit code = result; on failure, a Telegram message if configured. |
| `exocortex-e2e.timer` | 01:15 every night. |

Both containers use `Pull=newer`, so each run uses the latest images.

## Install

The image carries these files; the server gets no source code.

```sh
tmp=$(mktemp -d)
podman run --rm --entrypoint sh -v "$tmp:/out:Z" ghcr.io/hretheum/exocortex-e2e:main \
  -c 'cp -r /opt/exocortex/deploy/e2e/. /out/'
mkdir -p ~/.config/containers/systemd/exocortex-e2e ~/.config/systemd/user ~/.config/exocortex-e2e
cp "$tmp"/quadlet/* ~/.config/containers/systemd/exocortex-e2e/
cp "$tmp"/systemd/* ~/.config/systemd/user/
cp -n "$tmp"/e2e.env.example ~/.config/exocortex-e2e/e2e.env && chmod 600 ~/.config/exocortex-e2e/e2e.env
rm -rf "$tmp"
```

Set `TELEGRAM_CHAT_ID` in `e2e.env`. The bot token is the podman secret
`gate_telegram_token` shared with the publishing gate
(`printf none | podman secret create gate_telegram_token -` disables alerts).

```sh
systemctl --user daemon-reload
systemctl --user start exocortex-e2e.service      # first run by hand
journalctl --user -u exocortex-e2e.service -n 50
systemctl --user enable --now exocortex-e2e.timer
```

## Changing the model

The chat model is set in `config/llm_routing.selfhosted.yaml` inside the
image. To use another one, put a routing file on the server and mount it with
a drop-in, e.g. `~/.config/containers/systemd/exocortex-e2e.container.d/model.conf`:

```ini
[Container]
Volume=%h/.config/exocortex-e2e/llm_routing.yaml:/opt/exocortex/config/llm_routing.selfhosted.yaml:ro,Z
```

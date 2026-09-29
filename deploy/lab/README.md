# Exocortex lab on the home server (rootless Podman, Quadlet)

The lab runs on the same server as the private Exocortex instance, so the
separation has to hold even when someone makes a mistake (roadmap task F2.1).

| File | What it does |
|---|---|
| `exocortex-lab.network` | Internal network: no route to the host, the LAN or the internet. |
| `exocortex-lab-db.container` + `.volume` | Lab database (the `exocortex-db` image) with its own container, password and volume. No published port. |
| `exocortex-lab-migrate.container` | Schema migrations from the public engine image. On demand and before the API starts. |
| `exocortex-lab-api.container` | Lab Capture API, on the lab network only. Sees only the published documents folder of the vault, read-only. |
| `exocortex-lab-llm.container` + `.volume` | Gateway to the local model server. Not on the lab network: its own network namespace forwards only the model server's port on the host loopback (`pasta -T 8080`). Lab processes talk to it through a Unix socket in the volume. Three calls (`/v1/models`, `/v1/chat/completions`, `/v1/embeddings`) for the models in `lab/models.yaml`; everything else is refused. |
| `exocortex-lab-fetch.container` + `.volume` | Gateway for downloads from allowed sources. Not on the lab network: its own network namespace reaches the internet only (no host ports). Lab jobs talk to it through a Unix socket in the volume. |
| `exocortex-lab-sync.container` + `.timer` | Every 15 minutes: documents, hypothesis cards and gate decisions into the lab, data export and result pages into the `exocortex-lab-out` volume, which the publisher reads. |
| `exocortex-lab-radar.container` + `.timer` | Sunday 22:30: radar channels into the lab graph, the week's radar page and the first scoring of its candidates by three model families (F5.1 to F5.3). |
| `exocortex-lab-isolation.container` + `.timer` | 03:40 every night: from inside the lab, every known address of the private database and of the outside world must refuse a TCP connection, no private vault folder may be visible, the lab database must answer, and the model gateway must refuse other paths, other models and absolute-form targets. |

The units come from the engine image (`/opt/exocortex/deploy/lab/`); the
server gets no source code.

## Install

```sh
tmp=$(mktemp -d)
podman run --rm --entrypoint sh -v "$tmp:/out:Z" ghcr.io/hretheum/exocortex-public:main \
  -c 'cp -r /opt/exocortex/deploy/lab/. /out/'
mkdir -p ~/.config/containers/systemd/exocortex-lab ~/.config/systemd/user ~/.config/exocortex-lab
cp "$tmp"/quadlet/* ~/.config/containers/systemd/exocortex-lab/
cp "$tmp"/systemd/* ~/.config/systemd/user/
cp -n "$tmp"/lab.env.example ~/.config/exocortex-lab/lab.env && chmod 600 ~/.config/exocortex-lab/lab.env
rm -rf "$tmp"

pw=$(openssl rand -hex 24)
printf %s "$pw" | podman secret create lab_db_password -
printf %s "postgresql://exocortex:$pw@exocortex-lab-db:5432/exocortex" | podman secret create lab_database_url -
openssl rand -hex 24 | tr -d '\n' | podman secret create lab_capture_token -
unset pw

systemctl --user daemon-reload
systemctl --user start exocortex-lab-db exocortex-lab-migrate exocortex-lab-api exocortex-lab-llm
systemctl --user start exocortex-lab-isolation     # expect "status": "pass"
systemctl --user enable --now exocortex-lab-isolation.timer
```

Add the server's LAN addresses to `LAB_PRIVATE_DB_TARGETS` in `lab.env`.

## Paths out of the lab

The lab network is internal. Every path out is explicit and checked every
night by the isolation check:

| Path | How | What it allows |
|---|---|---|
| Local models | `exocortex-lab-llm`, Unix socket in the `exocortex-lab-llm` volume | the three calls above, for models listed in `lab/models.yaml` with their license |
| Public sources | `exocortex-lab-fetch`, Unix socket in the `exocortex-lab-fetch` volume | `GET /fetch?url=` for https URLs on `lab/sources.yaml`, keeping each source's pause between requests; redirects only to allowed URLs |

Adding a model is a commit to `lab/models.yaml` with the license and where
it was checked. The gateway itself holds no credentials, takes no target
from a request, follows no redirects and logs one line per request without
prompts or answers.

## Lab jobs

Every job runs from the engine image on the lab network, prints one JSON
document and exits. For example:

```sh
lab() {
  podman run --rm --network exocortex-lab --env-file ~/.config/exocortex-lab/lab.env \
    --secret lab_database_url,type=env,target=DATABASE_URL \
    -v ~/vault/_source/dowody:/vault/_source/dowody:ro,z \
    -v exocortex-lab-llm:/run/lab-llm:z \
    ghcr.io/hretheum/exocortex-public:main exocortex lab "$@"
}
lab docs-sync                                   # published documents -> lab graph
lab corpus-graph --corpus intent-vs-fact --embed  # corpus papers -> lab graph (F3.2)
lab toy run --sample tuning                     # toy experiment through the queue (F2.6)
lab work                                        # drain the queue, grouped by model
lab signals --embed                             # radar channels through the fetch gateway (F5.2)
```

Jobs that download mount the fetch volume as well:
`-v exocortex-lab-fetch:/run/lab-fetch:z`.

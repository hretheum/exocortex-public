# lab-site-repo

Deployment repository of https://lab.exocortex.zone (Exocortex R&D). It holds only the workflow that
builds the site from [exocortex-public](https://github.com/hretheum/exocortex-public) (folder `lab-site/`)
and the phase labels in `state.json`. Edit `state.json` to change a phase label. The site is rebuilt
every hour and on every push, once exocortex-public is public.

Setup: Settings, Pages, source "GitHub Actions"; custom domain `lab.exocortex.zone`; enforce HTTPS.
DNS: a `CNAME` record `lab` pointing to `hretheum.github.io`.

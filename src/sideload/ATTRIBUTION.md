# Attribution — Sideloading Engine

The Apple ID authentication (GrandSlam/SRP), anisette provisioning,
developer-services provisioning, and zsign-based signing code in
`src/sideload/ipaside_engine/` is adapted from **iPASide** by pwnapplehat,
licensed under the **MIT License** (full text in
`ipaside_engine/LICENSE-MIT-ipaside`).

- Upstream: https://github.com/pwnapplehat/ipaside
- Copyright (c) pwnapplehat (see LICENSE-MIT-ipaside for the full notice)

Changes made for WorkSlop Desktop:
- Package relocated to `src.sideload.ipaside_engine`
- Per-user data directory renamed to `WorkSlopDesktop`
- `WORKSLOP_ZSIGN` accepted as an alias for the zsign override env var

The MIT license requires the copyright notice to be preserved, which it is
in `LICENSE-MIT-ipaside`. This project as a whole remains AGPL-3.0; MIT
code is compatible with that.

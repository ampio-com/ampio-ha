# Core handoff

A draft Ampio Core PR already exists at https://github.com/home-assistant/core/pull/179548. Resolve ownership and coordinate with its author before opening another PR for the same `ampio` domain.

The HACS pilot contains several platforms. The first Home Assistant Core PR should carry one useful platform (switch), dynamic catalog handling, config flow, translations and tests. Publish the package in `packages/ampio-python` to PyPI with public source, issue tracker, sdist and wheel before opening the PR. Pin that package in Core's manifest. Do not copy the whole HACS pilot into Core in one PR.

Before claiming Bronze, verify every rule in `quality_scale.yaml` in the Core tree, including applicable exemptions for action setup, polling, actions, triggers and conditions. Submit separate PRs to `home-assistant/brands` and `home-assistant.io` with installation and removal instructions. Run Core's pre-commit and commit all generated changes. Validate the first PR on a real server and current HA against the official [Core contribution guide](https://developers.home-assistant.io/docs/core/integration/contributing_to_core/).

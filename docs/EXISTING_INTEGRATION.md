# Existing community Ampio integration

As of 2026-10-13, an independent project already exists:

- <https://github.com/pszypowicz/ampio-homeassistant> — HACS integration using the `ampio` domain. It documents sensor, binary sensor, light, cover, switch, button, climate, scene, siren and number support. It is unaffiliated with Ampio.
- <https://github.com/pszypowicz/ampio-mqtt> — public async Python library, published to PyPI as `ampio-mqtt`.
- <https://github.com/home-assistant/core/pull/179548> — draft Core PR for a sensor-only first integration.

This repository is a separate local implementation using the official Ampio server's DB-object protocol and proposed `ha` command-source marker. Installing two integrations with domain `ampio` in the same Home Assistant instance is not supported. Before publishing or migrating users, decide whether this code becomes an official Ampio integration, joins the existing project, or is reduced to backend and protocol contributions. Check the upstream project's current status again at that time.

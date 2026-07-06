# Local HWCTF Platform

This directory contains a local Python implementation of the Agent API described in `API.md`.
It supports dynamic Web and Pwn challenge envs without external services.

## Run

```powershell
python run.py --host 127.0.0.1 --port 8000 --pwn-port 9005 --reset-state
```

Default values:

- API endpoint: `http://127.0.0.1:8000/api/v1`
- Agent key: `local-agent-key`
- Pwn TCP gateway: `127.0.0.1:9005`

## API Examples

```powershell
$env:HWCTF_API_ENDPOINT = "http://127.0.0.1:8000/api/v1"
$env:HWCTF_AGENT_KEY = "local-agent-key"

curl.exe -H "X-Agent-Key: $env:HWCTF_AGENT_KEY" "$env:HWCTF_API_ENDPOINT/agent/team/profile"
curl.exe -H "X-Agent-Key: $env:HWCTF_AGENT_KEY" "$env:HWCTF_API_ENDPOINT/agent/challenges"
```

Start a Web env:

```powershell
curl.exe -X POST -H "X-Agent-Key: $env:HWCTF_AGENT_KEY" "$env:HWCTF_API_ENDPOINT/agent/challenges/101/env"
```

Open the returned `env.url` in a browser or curl it with `X-Agent-Key`.

Start a Pwn env:

```powershell
curl.exe -X POST -H "X-Agent-Key: $env:HWCTF_AGENT_KEY" "$env:HWCTF_API_ENDPOINT/agent/challenges/201/env"
```

Connect to the returned `host` and `port`, then send `routing_header` as the first line.

## Smoke Test

In another terminal while the server is running:

```powershell
python scripts/smoke_test.py
```

For one executable example per API request:

```powershell
python scripts/api_request_examples.py
```

Human-readable curl examples are in `API_TEST_EXAMPLES.md`.

## Challenge Data

- `data/challenges.json` defines challenge metadata, flags, hints, and attachments.
- `data/teams.json` defines local teams and Agent keys.
- `data/state.json` is created automatically for env state, solves, and scores.

The API never exposes flags through list/detail endpoints. Flags are only reachable through dynamic challenge services and then submitted to `/agent/challenges/<challenge_id>/submit`.

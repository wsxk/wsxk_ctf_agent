from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from .config import ServerConfig
from .errors import bad_request, env_not_running, not_found


JsonDict = dict[str, Any]


class PlatformStore:
    def __init__(self, config: ServerConfig) -> None:
        self.config = config
        self.base_dir = config.base_dir
        self.data_dir = self.base_dir / "data"
        self.challenges_path = self.data_dir / "challenges.json"
        self.teams_path = self.data_dir / "teams.json"
        self.state_path = self.data_dir / "state.json"
        self.lock = threading.RLock()
        self.challenges = self._load_json_list(self.challenges_path)
        self.teams = self._load_json_list(self.teams_path)
        self.state = self._load_state()
        self._validate_data()

    def _load_json_list(self, path: Path) -> list[JsonDict]:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, list):
            raise ValueError(f"{path} must contain a JSON list")
        return data

    def _load_state(self) -> JsonDict:
        if not self.state_path.exists():
            return {"team_state": {}, "envs": {}, "flag_solves": {}}
        with self.state_path.open("r", encoding="utf-8") as fh:
            state = json.load(fh)
        state.setdefault("team_state", {})
        state.setdefault("envs", {})
        state.setdefault("flag_solves", {})
        return state

    def _save_state(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = self.state_path.with_suffix(".json.tmp")
        with tmp_path.open("w", encoding="utf-8") as fh:
            json.dump(self.state, fh, indent=2, ensure_ascii=False, sort_keys=True)
            fh.write("\n")
        os.replace(tmp_path, self.state_path)

    def _validate_data(self) -> None:
        seen_challenges: set[int] = set()
        seen_files: set[int] = set()
        for challenge in self.challenges:
            cid = int(challenge["id"])
            if cid in seen_challenges:
                raise ValueError(f"duplicate challenge id: {cid}")
            seen_challenges.add(cid)
            for file_item in challenge.get("files", []):
                fid = int(file_item["id"])
                if fid in seen_files:
                    raise ValueError(f"duplicate file id: {fid}")
                seen_files.add(fid)
        seen_keys: set[str] = set()
        for team in self.teams:
            key = str(team["agent_key"])
            if key in seen_keys:
                raise ValueError(f"duplicate agent_key: {key}")
            seen_keys.add(key)

    def get_team_by_key(self, agent_key: str | None) -> JsonDict | None:
        if not agent_key:
            return None
        for team in self.teams:
            if team.get("agent_key") == agent_key:
                return {"id": int(team["id"]), "name": str(team["name"]), "agent_key": agent_key}
        return None

    def get_challenge(self, challenge_id: int) -> JsonDict:
        for challenge in self.challenges:
            if int(challenge["id"]) == int(challenge_id):
                return challenge
        raise not_found("challenge not found")

    def _team_state(self, agent_key: str) -> JsonDict:
        teams = self.state.setdefault("team_state", {})
        return teams.setdefault(agent_key, {"score": 0, "progress": {}})

    def _progress(self, agent_key: str, challenge_id: int) -> JsonDict:
        team_state = self._team_state(agent_key)
        progress = team_state.setdefault("progress", {})
        return progress.setdefault(str(challenge_id), {"solved_flags": [], "unlocked_hints": []})

    def _challenge_penalty(self, progress: JsonDict, challenge: JsonDict) -> float:
        unlocked = {int(value) for value in progress.get("unlocked_hints", [])}
        penalty = 0.0
        for hint in challenge.get("hints", []):
            if int(hint["id"]) in unlocked:
                penalty += float(hint.get("penalty_percent", 0.2))
        return min(penalty, 0.8)

    def score_if_solved_now(self, agent_key: str, challenge: JsonDict) -> int:
        progress = self._progress(agent_key, int(challenge["id"]))
        if self._is_completed(progress, challenge):
            return 0
        base_score = int(challenge.get("base_score", 500))
        return max(0, int(round(base_score * (1.0 - self._challenge_penalty(progress, challenge)))))

    def next_flag_score(self, agent_key: str, challenge: JsonDict) -> int:
        progress = self._progress(agent_key, int(challenge["id"]))
        if self._is_completed(progress, challenge):
            return 0
        flag_total = max(1, len(challenge.get("flags", [])))
        rank = self._next_flag_rank(int(challenge["id"]), self._first_unsolved_flag_index(progress, challenge))
        base = self.score_if_solved_now(agent_key, challenge) / flag_total
        return int(round(base * self._rank_multiplier(rank)))

    def _first_unsolved_flag_index(self, progress: JsonDict, challenge: JsonDict) -> int:
        solved = {int(value) for value in progress.get("solved_flags", [])}
        for index in range(len(challenge.get("flags", []))):
            if index not in solved:
                return index
        return max(0, len(challenge.get("flags", [])) - 1)

    def _next_flag_rank(self, challenge_id: int, flag_index: int) -> int:
        key = f"{challenge_id}:{flag_index}"
        return int(self.state.setdefault("flag_solves", {}).get(key, 0)) + 1

    def _rank_multiplier(self, rank: int) -> float:
        return max(0.2, 0.95 ** max(rank - 1, 0))

    def _is_completed(self, progress: JsonDict, challenge: JsonDict) -> bool:
        return len(progress.get("solved_flags", [])) >= len(challenge.get("flags", []))

    def _status(self, progress: JsonDict, challenge: JsonDict) -> str:
        if self._is_completed(progress, challenge):
            return "solved"
        if progress.get("solved_flags"):
            return "partial"
        return "unsolved"

    def _serialize_hints(self, agent_key: str, challenge: JsonDict, include_unlocked_content: bool) -> list[JsonDict]:
        progress = self._progress(agent_key, int(challenge["id"]))
        unlocked = {int(value) for value in progress.get("unlocked_hints", [])}
        hints: list[JsonDict] = []
        for hint in challenge.get("hints", []):
            item = {
                "id": int(hint["id"]),
                "title": str(hint.get("title", f"hint-{hint['id']}")),
                "unlocked": int(hint["id"]) in unlocked,
            }
            if include_unlocked_content and item["unlocked"]:
                item["content"] = str(hint.get("content", ""))
                item["penalty_percent"] = float(hint.get("penalty_percent", 0.2))
            hints.append(item)
        return hints

    def _serialize_files(self, challenge: JsonDict) -> list[JsonDict]:
        files: list[JsonDict] = []
        for file_item in challenge.get("files", []):
            rel_path = Path(str(file_item["path"]))
            full_path = (self.base_dir / rel_path).resolve()
            size = full_path.stat().st_size if full_path.exists() else int(file_item.get("size", 0))
            fid = int(file_item["id"])
            files.append(
                {
                    "id": fid,
                    "filename": str(file_item["filename"]),
                    "size": size,
                    "download_url": f"/api/v1/challenge-platform/files/{fid}/download",
                }
            )
        return files

    def challenge_summary(self, agent_key: str, challenge: JsonDict) -> JsonDict:
        cid = int(challenge["id"])
        progress = self._progress(agent_key, cid)
        return {
            "id": cid,
            "name": str(challenge["name"]),
            "category": str(challenge["category"]),
            "description": str(challenge.get("description", "")),
            "score_if_solved_now": self.score_if_solved_now(agent_key, challenge),
            "next_flag_score": self.next_flag_score(agent_key, challenge),
            "flag_total": len(challenge.get("flags", [])),
            "flag_solved": len(progress.get("solved_flags", [])),
            "status": self._status(progress, challenge),
            "env_type": str(challenge.get("env_type", "dynamic_container")),
            "hints": self._serialize_hints(agent_key, challenge, include_unlocked_content=False),
        }

    def challenge_detail(self, agent_key: str, challenge_id: int) -> JsonDict:
        with self.lock:
            challenge = self.get_challenge(challenge_id)
            detail = self.challenge_summary(agent_key, challenge)
            detail["files"] = self._serialize_files(challenge)
            detail["hints"] = self._serialize_hints(agent_key, challenge, include_unlocked_content=True)
            return detail

    def list_challenges(self, agent_key: str) -> list[JsonDict]:
        with self.lock:
            return [self.challenge_summary(agent_key, challenge) for challenge in self.challenges]

    def unlock_hint(self, agent_key: str, challenge_id: int, hint_id: int) -> JsonDict:
        with self.lock:
            challenge = self.get_challenge(challenge_id)
            hint = None
            for candidate in challenge.get("hints", []):
                if int(candidate["id"]) == int(hint_id):
                    hint = candidate
                    break
            if hint is None:
                raise not_found("hint not found")
            progress = self._progress(agent_key, challenge_id)
            unlocked = progress.setdefault("unlocked_hints", [])
            if int(hint_id) not in {int(value) for value in unlocked}:
                unlocked.append(int(hint_id))
                self._save_state()
            return {
                "id": int(hint["id"]),
                "content": str(hint.get("content", "")),
                "penalty_percent": float(hint.get("penalty_percent", 0.2)),
            }

    def submit_flag(self, agent_key: str, challenge_id: int, submitted_flag: str) -> JsonDict:
        with self.lock:
            challenge = self.get_challenge(challenge_id)
            flags = [str(flag) for flag in challenge.get("flags", [])]
            if not isinstance(submitted_flag, str) or not submitted_flag:
                raise bad_request("flag must be a non-empty string")
            if submitted_flag not in flags:
                progress = self._progress(agent_key, challenge_id)
                return {
                    "correct": False,
                    "completed": self._is_completed(progress, challenge),
                    "flag_rank": None,
                    "flag_solved": len(progress.get("solved_flags", [])),
                    "flag_total": len(flags),
                    "awarded_score": 0,
                }

            flag_index = flags.index(submitted_flag)
            progress = self._progress(agent_key, challenge_id)
            solved = {int(value) for value in progress.get("solved_flags", [])}
            already_solved = flag_index in solved
            solves_key = f"{challenge_id}:{flag_index}"
            flag_rank = int(self.state.setdefault("flag_solves", {}).get(solves_key, 0))

            awarded = 0
            if not already_solved:
                flag_rank += 1
                self.state["flag_solves"][solves_key] = flag_rank
                flag_total = max(1, len(flags))
                per_flag = self.score_if_solved_now(agent_key, challenge) / flag_total
                awarded = int(round(per_flag * self._rank_multiplier(flag_rank)))
                progress.setdefault("solved_flags", []).append(flag_index)
                team_state = self._team_state(agent_key)
                team_state["score"] = int(team_state.get("score", 0)) + awarded
                if self._is_completed(progress, challenge):
                    self._stop_env_for_challenge(agent_key, challenge_id)
                self._save_state()

            return {
                "correct": True,
                "completed": self._is_completed(progress, challenge),
                "flag_rank": flag_rank,
                "flag_solved": len(progress.get("solved_flags", [])),
                "flag_total": len(flags),
                "awarded_score": awarded,
            }

    def _public_env(self, env: JsonDict) -> JsonDict:
        return {
            "external_env_id": env["external_env_id"],
            "challenge_id": int(env["challenge_id"]),
            "status": str(env["status"]),
            "url": str(env["url"]),
            "host": str(env["host"]),
            "port": int(env["port"]),
            "protocol": str(env["protocol"]),
            "expose_mode": str(env["expose_mode"]),
            "routing_header": env.get("routing_header"),
        }

    def _running_envs_for_team(self, agent_key: str) -> list[JsonDict]:
        return [
            env
            for env in self.state.setdefault("envs", {}).values()
            if env.get("agent_key") == agent_key and env.get("status") == "running"
        ]

    def list_envs(self, agent_key: str) -> list[JsonDict]:
        with self.lock:
            return [self._public_env(env) for env in self._running_envs_for_team(agent_key)]

    def get_env_for_challenge(self, agent_key: str, challenge_id: int) -> JsonDict | None:
        with self.lock:
            for env in self._running_envs_for_team(agent_key):
                if int(env["challenge_id"]) == int(challenge_id):
                    return self._public_env(env)
            return None

    def get_env(self, env_id: str) -> JsonDict:
        env = self.state.setdefault("envs", {}).get(env_id)
        if not env:
            raise not_found("env not found")
        return env

    def start_env(self, agent_key: str, challenge_id: int) -> JsonDict:
        with self.lock:
            challenge = self.get_challenge(challenge_id)
            running = self._running_envs_for_team(agent_key)
            for env in running:
                if int(env["challenge_id"]) == int(challenge_id):
                    return self._public_env(env)
            if running:
                active = running[0]
                raise bad_request(
                    f"team already has a running env for challenge {active['challenge_id']}",
                    "Stop the current env before starting another challenge env.",
                    status=409,
                )

            env_id = f"env_{uuid.uuid4().hex[:12]}"
            category = str(challenge["category"])
            if category == "web":
                env = {
                    "external_env_id": env_id,
                    "agent_key": agent_key,
                    "challenge_id": int(challenge_id),
                    "category": category,
                    "status": "running",
                    "url": f"{self.config.http_origin}/e/{env_id}/",
                    "host": self.config.public_host,
                    "port": self.config.port,
                    "protocol": "http",
                    "expose_mode": "http_proxy",
                    "routing_header": None,
                    "created_at": int(time.time()),
                }
            elif category == "pwn":
                env = {
                    "external_env_id": env_id,
                    "agent_key": agent_key,
                    "challenge_id": int(challenge_id),
                    "category": category,
                    "status": "running",
                    "url": self.config.tcp_url,
                    "host": self.config.public_host,
                    "port": self.config.pwn_port,
                    "protocol": "tcp",
                    "expose_mode": "tcp_gateway",
                    "routing_header": f"HWCTF {env_id} {agent_key}",
                    "created_at": int(time.time()),
                }
            else:
                raise bad_request(f"unsupported dynamic category: {category}")

            self.state.setdefault("envs", {})[env_id] = env
            self._save_state()
            return self._public_env(env)

    def stop_env(self, agent_key: str, env_id: str) -> JsonDict:
        with self.lock:
            env = self.get_env(env_id)
            if env.get("agent_key") != agent_key:
                raise not_found("env not found")
            if env.get("status") != "running":
                raise env_not_running("env is not running")
            env["status"] = "stopped"
            env["stopped_at"] = int(time.time())
            self._save_state()
            return self._public_env(env)

    def _stop_env_for_challenge(self, agent_key: str, challenge_id: int) -> None:
        for env in self._running_envs_for_team(agent_key):
            if int(env["challenge_id"]) == int(challenge_id):
                env["status"] = "stopped"
                env["stopped_at"] = int(time.time())

    def get_running_env_for_access(self, agent_key: str, env_id: str) -> JsonDict:
        with self.lock:
            env = self.get_env(env_id)
            if env.get("agent_key") != agent_key:
                raise not_found("env not found")
            if env.get("status") != "running":
                raise env_not_running("env is not running")
            return dict(env)

    def get_env_for_routing(self, env_id: str, agent_key: str) -> JsonDict | None:
        with self.lock:
            env = self.state.setdefault("envs", {}).get(env_id)
            if not env:
                return None
            if env.get("agent_key") != agent_key or env.get("status") != "running":
                return None
            return dict(env)

    def get_file(self, file_id: int) -> tuple[Path, str]:
        with self.lock:
            for challenge in self.challenges:
                for file_item in challenge.get("files", []):
                    if int(file_item["id"]) == int(file_id):
                        full_path = (self.base_dir / str(file_item["path"])).resolve()
                        if not full_path.exists() or not full_path.is_file():
                            raise not_found("file not found")
                        return full_path, str(file_item["filename"])
            raise not_found("file not found")

    def scoreboard(self) -> list[JsonDict]:
        with self.lock:
            rows: list[JsonDict] = []
            for team in self.teams:
                agent_key = str(team["agent_key"])
                score = int(self._team_state(agent_key).get("score", 0))
                rows.append({"team_name": str(team["name"]), "score": score})
            rows.sort(key=lambda row: (-row["score"], row["team_name"]))
            for index, row in enumerate(rows, start=1):
                row["rank"] = index
            return rows

    def reset_state(self) -> None:
        with self.lock:
            self.state = {"team_state": {}, "envs": {}, "flag_solves": {}}
            self._save_state()

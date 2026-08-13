"""In-memory replacement for :class:`examples.uavs_strategy.redis_modules.uav_redis_io.UavRedisIO`.

The original simulator used Redis as the shared state between independent
SPADE agents.  The pure Python version runs all agents inside one process,
so a plain dictionary is both faster and simpler.  This class intentionally
keeps the same method names so the rest of the code can be migrated with
minimal changes.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Iterable, List, Optional

import numpy as np


def _now_ms() -> int:
    return int(time.time() * 1000)


class InMemoryUavIO:
    """Store UAV positions, trajectories, lookahead and coordination state in memory."""

    def __init__(self) -> None:
        self.clear()

    def clear(self) -> None:
        self._kv: Dict[str, Any] = {}
        self._blue_ids: set[str] = set()
        self._red_ids: set[str] = set()

    # ------------------------------------------------------------------
    # ID management
    # ------------------------------------------------------------------
    def add_uav_id(self, uid: str, blue: bool = True) -> None:
        (self._blue_ids if blue else self._red_ids).add(uid)

    def remove_uav_id(self, uid: str, blue: bool = True) -> None:
        (self._blue_ids if blue else self._red_ids).discard(uid)

    def get_ids(self, blue: bool = True) -> set[str]:
        return set(self._blue_ids if blue else self._red_ids)

    def scan_ids_by_key(self, prefix: str) -> set[str]:
        # Kept for API compatibility; not needed by the pure path.
        return set()

    # ------------------------------------------------------------------
    # Position
    # ------------------------------------------------------------------
    def set_pos(
        self,
        uid: str,
        x: float,
        y: float,
        z: float,
        ts_ms: Optional[int] = None,
        blue: bool = True,
        recorded_at_ms: Optional[int] = None,
    ) -> None:
        wall = _now_ms() if recorded_at_ms is None else int(recorded_at_ms)
        self._kv[f"{uid}:pos"] = {
            "x": float(x),
            "y": float(y),
            "z": float(z),
            "ts": wall if ts_ms is None else int(ts_ms),
            "recordedAtMs": wall,
        }

    def get_pos(self, uid: str, blue: bool = True) -> Optional[Dict[str, Any]]:
        return self._kv.get(f"{uid}:pos")

    def mget_pos(self, ids: Iterable[str], blue: bool = True) -> Dict[str, Optional[Dict[str, Any]]]:
        return {uid: self._kv.get(f"{uid}:pos") for uid in ids}

    def mget_speed_from_traj(
        self,
        ids: Iterable[str],
        blue: bool = True,
        dt: float = 1.0,
    ) -> Dict[str, List[float]]:
        speeds: Dict[str, List[float]] = {}
        for uid in ids:
            traj = self.get_traj(uid)
            if len(traj) >= 3:
                p1 = np.asarray(traj[-2], dtype=float)
                p0 = np.asarray(traj[-3], dtype=float)
            elif len(traj) == 2:
                p1 = np.asarray(traj[-1], dtype=float)
                p0 = np.asarray(traj[-2], dtype=float)
            else:
                p1 = np.zeros(3)
                p0 = np.zeros(3)
            speeds[uid] = ((p1 - p0) / float(dt)).tolist()
        return speeds

    # ------------------------------------------------------------------
    # Trajectory
    # ------------------------------------------------------------------
    def set_traj(self, uid: str, points: List[List[float]]) -> None:
        self._kv[f"{uid}:traj"] = [list(p) for p in points]

    def append_traj_points(self, uid: str, points: List[float]) -> None:
        self._kv.setdefault(f"{uid}:traj", []).append(list(points))

    def get_traj(self, uid: str) -> List[List[float]]:
        return self._kv.get(f"{uid}:traj", [])

    def mget_traj(self, ids: Iterable[str], blue: bool = True) -> Dict[str, List[List[float]]]:
        return {uid: self._kv.get(f"{uid}:traj", []) for uid in ids}

    def clear_traj(self, uid: str) -> None:
        self._kv.pop(f"{uid}:traj", None)

    # ------------------------------------------------------------------
    # Reference trajectory
    # ------------------------------------------------------------------
    def set_ref_traj(self, uid: str, points: List[List[float]]) -> None:
        self._kv[f"{uid}:ref_traj"] = [list(p) for p in points]

    def get_ref_traj(self, uid: str) -> List[List[float]]:
        return self._kv.get(f"{uid}:ref_traj", [])

    def set_members_ref_traj(self, master_uid: str, members_traj: List[List[List[float]]]) -> None:
        for i, traj in enumerate(members_traj or []):
            sub_uid = f"{master_uid}_sub_{i}"
            self.set_ref_traj(sub_uid, traj)
            self.add_uav_id(sub_uid, blue=True)
            if traj and not self.get_pos(sub_uid, blue=True):
                self.set_pos(sub_uid, traj[0][0], traj[0][1], traj[0][2])
                self.set_lookahead(sub_uid, 0)

    def set_nodes_pair_base_ref_traj(self, uid_from: str, uid_to: str, traj: List[List[float]]) -> None:
        self._kv[f"{uid_from}_to_{uid_to}_base"] = [list(p) for p in traj]

    def get_nodes_pair_base_ref_traj(self, uid_from: str, uid_to: str) -> List[List[float]]:
        return self._kv.get(f"{uid_from}_to_{uid_to}_base", [])

    def set_nodes_pair_member_traj(
        self,
        uid_from: str,
        uid_to: str,
        member_id: str,
        traj: List[List[float]],
    ) -> None:
        self._kv[f"{uid_from}_to_{uid_to}_{member_id}"] = [list(p) for p in traj]

    def get_nodes_pair_member_traj(
        self,
        uid_from: str,
        uid_to: str,
        member_id: str,
    ) -> List[List[float]]:
        return self._kv.get(f"{uid_from}_to_{uid_to}_{member_id}", [])

    # ------------------------------------------------------------------
    # Lookahead and distance
    # ------------------------------------------------------------------
    def set_lookahead(self, uid: str, idx: int) -> None:
        self._kv[f"{uid}:lookahead"] = int(idx)

    def get_lookahead(self, uid: str) -> int:
        return int(self._kv.get(f"{uid}:lookahead", 0))

    def get_dist_2d(self, uid: str) -> Optional[float]:
        pos = self.get_pos(uid)
        traj = self.get_traj(uid)
        if not pos or not traj:
            return None
        end = traj[-1]
        return float(((pos["x"] - end[0]) ** 2 + (pos["y"] - end[1]) ** 2) ** 0.5)

    # ------------------------------------------------------------------
    # Coordination state
    # ------------------------------------------------------------------
    def set_uav_state(self, uid: str, state_key: str, state_value: str) -> None:
        self._kv[f"{uid}:state:{state_key}"] = state_value

    def get_uav_state(self, uid: str, state_key: str) -> Optional[str]:
        return self._kv.get(f"{uid}:state:{state_key}")

    def mget_uav_states(self, uids: List[str], state_key: str) -> Dict[str, Optional[str]]:
        return {uid: self._kv.get(f"{uid}:state:{state_key}") for uid in uids}

    WORLD_UID = "__world__"

    def set_world_state(self, key: str, value: Any) -> None:
        self.set_uav_state(self.WORLD_UID, key, str(value))

    def get_world_state(self, key: str) -> Optional[str]:
        return self.get_uav_state(self.WORLD_UID, key)

    def init_world_round(self, initial_round: int = 0) -> None:
        if self.get_world_state("sim_round") is None:
            self.set_world_state("sim_round", initial_round)

    def set_uav_sync_state(self, uid: str, is_synced: bool) -> None:
        self._kv[f"{uid}:state:sync"] = str(is_synced)

    def get_uav_sync_state(self, uid: str) -> bool:
        return self._kv.get(f"{uid}:state:sync") == "True"

    def set_flag(self, key: str, value: Any) -> None:
        self._kv[key] = value

    def get_flag(self, key: str) -> Any:
        return self._kv.get(key)

    # ------------------------------------------------------------------
    # Trajectory metadata
    # ------------------------------------------------------------------
    def set_traj_extra(self, uid: str, extra_list: List[Dict[str, Any]]) -> None:
        self._kv[f"{uid}:traj_extra"] = list(extra_list)

    def append_traj_extra(self, uid: str, extra_info: Dict[str, Any]) -> None:
        self._kv.setdefault(f"{uid}:traj_extra", []).append(extra_info)

    def get_traj_extra(self, uid: str) -> List[Dict[str, Any]]:
        return self._kv.get(f"{uid}:traj_extra", [])

    def append_pos_traj_with_extra(
        self,
        uid: str,
        pos: List[float],
        extra_info: Dict[str, Any],
        blue: bool = True,
    ) -> None:
        wall = int(extra_info.get("recordedAtMs", _now_ms()))
        sim = int(extra_info.get("simTimeMs", wall))
        self._kv[f"{uid}:pos"] = {
            "x": float(pos[0]),
            "y": float(pos[1]),
            "z": float(pos[2]),
            "ts": sim,
            "recordedAtMs": wall,
        }
        self._kv.setdefault(f"{uid}:traj", []).append(list(pos))
        self._kv.setdefault(f"{uid}:traj_extra", []).append(extra_info)

    # ------------------------------------------------------------------
    # Aggregate helpers
    # ------------------------------------------------------------------
    def get_rendezvous_point(self, ids: List[str], blue: bool = True) -> Optional[List[float]]:
        positions = [self.get_pos(uid, blue=blue) for uid in ids]
        valid = [p for p in positions if p]
        if not valid:
            return None
        points = np.asarray([[p["x"], p["y"], p["z"]] for p in valid], dtype=float)
        return np.mean(points, axis=0).tolist()

    @staticmethod
    def filter_stale(
        pos_map: Dict[str, Optional[Dict[str, Any]]],
        stale_ms: int,
    ) -> Dict[str, Dict[str, Any]]:
        now = _now_ms()
        out: Dict[str, Dict[str, Any]] = {}
        for uid, pos in pos_map.items():
            if not pos:
                continue
            ts = int(pos.get("recordedAtMs", pos.get("ts", 0)))
            if abs(now - ts) <= stale_ms:
                out[uid] = pos
        return out

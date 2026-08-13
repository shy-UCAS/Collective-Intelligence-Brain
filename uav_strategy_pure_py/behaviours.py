"""Pure Python periodic behaviours for the UAV agents.

This is a port of ``SyncAPFStepEnhance`` and the small vector/kinematics
helpers from the original SPADE behaviour module.  The only external
dependency is NumPy; coordination state is read and written through
:class:`uav_strategy_pure_py.memory_io.InMemoryUavIO`.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np


DT = 0.5
STEP = 8.0
MAX_HORIZONTAL_SPEED_MPS = STEP / DT
MAX_CLIMB_RATE_MPS = 5.0
MAX_DESCENT_RATE_MPS = 5.0
K_ATT = 0.85
K_ATT_FORM = 1.5
K_REP = 2.5
CLOSE_TH = 3.0
CLOSE_TH_SYNC = 0.5  # 减小到0.5米，要求更精确的到达判定以保持队形


def v_sub(a, b):
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]


def v_add(a, b):
    return [a[0] + b[0], a[1] + b[1], a[2] + b[2]]


def v_scale(a, s):
    return [a[0] * s, a[1] * s, a[2] * s]


def v_norm(a):
    n = (a[0] ** 2 + a[1] ** 2 + a[2] ** 2) ** 0.5
    return n if n > 1e-9 else 1e-9


def v_unit(a):
    n = v_norm(a)
    return [a[0] / n, a[1] / n, a[2] / n]


def bounded_motion_step(
    current,
    target,
    dt=DT,
    max_horizontal_speed_mps=MAX_HORIZONTAL_SPEED_MPS,
    max_climb_rate_mps=MAX_CLIMB_RATE_MPS,
    max_descent_rate_mps=MAX_DESCENT_RATE_MPS,
):
    """Move toward ``target`` without exceeding per-round kinematic limits."""
    if dt <= 0:
        raise ValueError("dt must be positive")
    if min(max_horizontal_speed_mps, max_climb_rate_mps, max_descent_rate_mps) < 0:
        raise ValueError("speed and climb/descent limits must be non-negative")

    dx = float(target[0]) - float(current[0])
    dy = float(target[1]) - float(current[1])
    horizontal_distance = (dx * dx + dy * dy) ** 0.5
    max_horizontal_step = float(max_horizontal_speed_mps) * float(dt)
    if horizontal_distance <= max_horizontal_step or horizontal_distance <= 1e-9:
        next_x = float(target[0])
        next_y = float(target[1])
    else:
        scale = max_horizontal_step / horizontal_distance
        next_x = float(current[0]) + dx * scale
        next_y = float(current[1]) + dy * scale

    dz = float(target[2]) - float(current[2])
    max_up_step = float(max_climb_rate_mps) * float(dt)
    max_down_step = float(max_descent_rate_mps) * float(dt)
    bounded_dz = max(-max_down_step, min(max_up_step, dz))
    next_z = float(current[2]) + bounded_dz
    return [next_x, next_y, next_z]


class SyncAPFStepEnhance:
    """Enhanced APF step with a global-round lock and segment-start barrier."""

    VERBOSE = False

    def __init__(self, period: Optional[float] = None, agent: Any = None) -> None:
        self.period = period
        self.agent = agent

    def log(self, *args) -> None:
        from datetime import datetime

        ms_time = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        msg = f"[{ms_time}] " + " ".join(map(str, args))
        if self.VERBOSE:
            print(msg)
        if hasattr(self, "agent") and self.agent is not None:
            if not hasattr(self.agent, "step_logs"):
                self.agent.step_logs = []
            self.agent.step_logs.append(msg)

    # ------------------------------------------------------------------
    # Main entry
    # ------------------------------------------------------------------
    def run(self, current_round: Optional[int] = None) -> None:
        agent = self.agent
        io = agent.io

        if current_round is None:
            current_round = self._ensure_world_round_initialized(io)

        last_done = self._get_agent_round_done(agent, io)
        if last_done is not None and last_done == current_round:
            return

        if getattr(agent, "_waiting_for_deps", False):
            deps = getattr(agent, "current_depends_on", []) or []
            if all(io.get_flag(f"seg_done:{d}") == "1" for d in deps):
                agent._waiting_for_deps = False
                agent.can_task_start = True
                agent.request_planning()
                self.log(f"[{agent.self_uid}] deps satisfied, re-arm planning.")
            self._mark_agent_round_done(agent, io, current_round)
            return

        state = self._get_agent_state(agent, io)
        if not state:
            self.log(f"[{agent.self_uid}] Cannot get agent state, skipping round {current_round}.")
            self._mark_agent_round_done(agent, io, current_round)
            return

        me, traj, lookahead, max_idx, target, self_pos, _ = state

        if self._sync_state_checkpoint(agent, io, current_round):
            self.log(f"[{agent.self_uid}] Waiting at sync checkpoint. round={current_round}")
            self._record_wait_state(agent, io, target=target, current_round=current_round)
            self._mark_agent_round_done(agent, io, current_round)
            return

        state = self._get_agent_state(agent, io)
        if not state:
            self.log(
                f"[{agent.self_uid}] Cannot get agent state after checkpoint, "
                f"skipping round {current_round}."
            )
            self._mark_agent_round_done(agent, io, current_round)
            return

        me, traj, lookahead, max_idx, target, self_pos, dist2target = state
        nxt = self._calculate_physics(agent, io, target, self_pos)
        dist_after_move = v_norm(v_sub(target, nxt))

        self._update_status_and_redis(
            agent=agent,
            io=io,
            nxt=nxt,
            lookahead=lookahead,
            max_idx=max_idx,
            dist_to_target=dist_after_move,
            target=target,
            current_round=current_round,
        )
        self._mark_agent_round_done(agent, io, current_round)

    # ------------------------------------------------------------------
    # Round helpers
    # ------------------------------------------------------------------
    def _ensure_world_round_initialized(self, io) -> int:
        cur = io.get_world_state("sim_round")
        if cur is None:
            io.set_world_state("sim_round", 0)
            return 0
        return int(cur)

    def _get_current_round(self, io) -> int:
        cur = io.get_world_state("sim_round")
        if cur is None:
            raise ValueError("sim_round is not initialized")
        return int(cur)

    def _get_agent_round_done(self, agent, io) -> Optional[int]:
        val = self._get_single_uav_state(io, agent.self_uid, "round_done")
        if val is None or val == "":
            return None
        return int(val)

    def _mark_agent_round_done(self, agent, io, current_round: int) -> None:
        io.set_uav_state(agent.self_uid, "round_done", str(current_round))

    def _get_single_uav_state(self, io, uid: str, key: str):
        if hasattr(io, "get_uav_state"):
            return io.get_uav_state(uid, key)
        data = io.mget_uav_states([uid], key)
        return data.get(uid)

    def _get_segment_group_ids(self, agent) -> List[str]:
        peers = list(getattr(agent, "current_segment_siblings", []) or [])
        return sorted(set(peers + [agent.self_uid]))

    def _get_leader_id(self, agent) -> str:
        group_ids = self._get_segment_group_ids(agent)
        return group_ids[0] if group_ids else agent.self_uid

    # ------------------------------------------------------------------
    # Segment-start barrier
    # ------------------------------------------------------------------
    def _get_segment_release_info(self, agent, io):
        leader_id = self._get_leader_id(agent)
        release_key = self._get_single_uav_state(io, leader_id, "current_segment_release")
        release_round = self._get_single_uav_state(
            io, leader_id, "current_segment_release_round"
        )
        if release_round is not None and release_round != "":
            release_round = int(release_round)
        else:
            release_round = None
        return release_key, release_round

    def _set_segment_release_info(
        self,
        agent,
        io,
        segment_key: str,
        round_id: int,
    ) -> None:
        leader_id = self._get_leader_id(agent)
        io.set_uav_state(leader_id, "current_segment_release", segment_key)
        io.set_uav_state(leader_id, "current_segment_release_round", str(round_id))

    def _mark_arrived_at_segment_start(self, agent, io, segment_key: str) -> None:
        agent.has_synced_segment = True
        io.set_uav_state(agent.self_uid, "current_segment_sync", segment_key)
        io.set_uav_state(agent.self_uid, f"{segment_key}_segment_arrive", "arrived")

    def _all_group_arrived(self, agent, io, segment_key: str) -> bool:
        group_ids = self._get_segment_group_ids(agent)
        states = io.mget_uav_states(group_ids, "current_segment_sync")
        for pid in group_ids:
            if states.get(pid) != segment_key:
                self.log(
                    f"[{agent.self_uid}] Peer {pid} current_segment_sync={states.get(pid)} "
                    f"!= target segment {segment_key}"
                )
                return False
        return True

    def _get_frame_release_info(self, agent, io):
        leader_id = self._get_leader_id(agent)
        release_key = self._get_single_uav_state(io, leader_id, "current_frame_release")
        release_round = self._get_single_uav_state(
            io, leader_id, "current_frame_release_round"
        )
        if release_round is not None and release_round != "":
            release_round = int(release_round)
        else:
            release_round = None
        return release_key, release_round

    def _set_frame_release_info(
        self,
        agent,
        io,
        frame_key: str,
        round_id: int,
    ) -> None:
        leader_id = self._get_leader_id(agent)
        io.set_uav_state(leader_id, "current_frame_release", frame_key)
        io.set_uav_state(leader_id, "current_frame_release_round", str(round_id))

    def _all_group_frame_arrived(self, agent, io, frame_key: str) -> bool:
        group_ids = self._get_segment_group_ids(agent)
        states = io.mget_uav_states(group_ids, "current_frame_sync")
        for pid in group_ids:
            if states.get(pid) != frame_key:
                self.log(
                    f"[{agent.self_uid}] Peer {pid} current_frame_sync={states.get(pid)} "
                    f"!= target frame {frame_key}"
                )
                return False
        return True

    def _sync_state_checkpoint(self, agent, io, current_round: int) -> bool:
        state_val = "true" if getattr(agent, "can_task_start", False) else "false"
        io.set_uav_state(agent.self_uid, "can_task_start", state_val)

        lookahead = io.get_lookahead(agent.self_uid) or 0
        if lookahead > 0:
            return self._sync_frame_checkpoint(agent, io, current_round)

        state = self._get_agent_state(agent, io)
        if not state:
            raise ValueError("Cannot get agent state for checkpoint sync.")

        me, traj, lookahead, max_idx, target, self_pos, dist2target = state
        segment_key = getattr(agent, "current_segment_key", "unknown")
        my_sync_key = self._get_single_uav_state(io, agent.self_uid, "current_segment_sync")
        release_key, release_round = self._get_segment_release_info(agent, io)

        if (
            my_sync_key == segment_key
            and release_key == segment_key
            and release_round is not None
            and release_round < current_round
        ):
            io.set_lookahead(agent.self_uid, 1)
            self.log(
                f"[{agent.self_uid}] Consume release for segment={segment_key}, "
                f"release_round={release_round}, current_round={current_round}, "
                f"lookahead 0 -> 1"
            )
            return False

        if my_sync_key != segment_key and dist2target > CLOSE_TH_SYNC:
            self.log(
                f"[{agent.self_uid}] Not at segment start yet. "
                f"dist2target={dist2target:.3f} > CLOSE_TH_SYNC={CLOSE_TH_SYNC}"
            )
            return False

        if my_sync_key != segment_key and dist2target <= CLOSE_TH_SYNC:
            self._mark_arrived_at_segment_start(agent, io, segment_key)
            self.log(
                f"[{agent.self_uid}] Arrived at start and marked sync. "
                f"segment={segment_key}, round={current_round}"
            )
            return True

        group_ids = self._get_segment_group_ids(agent)
        if len(group_ids) <= 1:
            io.set_lookahead(agent.self_uid, 1)
            self.log(f"[{agent.self_uid}] Single-agent segment, lookahead 0 -> 1")
            return False

        if not self._all_group_arrived(agent, io, segment_key):
            self.log(
                f"[{agent.self_uid}] Waiting for all peers to arrive. "
                f"group={group_ids}, segment={segment_key}"
            )
            return True

        if release_key != segment_key:
            self._set_segment_release_info(agent, io, segment_key, current_round)
            self.log(
                f"[{agent.self_uid}] All peers arrived. "
                f"Release latched for segment={segment_key}, release_round={current_round}. "
                f"This round still waits."
            )
            return True

        self.log(
            f"[{agent.self_uid}] Release exists but not consumable yet. "
            f"segment={segment_key}, release_round={release_round}, current_round={current_round}"
        )
        return True

    def _sync_frame_checkpoint(self, agent, io, current_round: int) -> bool:
        """Barrier for every waypoint after the segment-start barrier.

        The segment-start barrier only aligns ``lookahead == 0``.  Without a
        second barrier the members would advance ``lookahead`` independently
        as soon as their own distance to the current waypoint is within
        ``CLOSE_TH_SYNC``.  This method mirrors the segment-start latch for
        each frame so all members of a formation advance to the next waypoint
        in the same simulation round.
        """
        state = self._get_agent_state(agent, io)
        if not state:
            raise ValueError("Cannot get agent state for frame sync.")

        me, traj, lookahead, max_idx, target, self_pos, dist2target = state
        group_ids = self._get_segment_group_ids(agent)

        # A single-agent segment does not need a formation barrier; keep the
        # original independent advancement behaviour.
        if len(group_ids) <= 1:
            if dist2target <= CLOSE_TH_SYNC and lookahead < max_idx:
                self.log(
                    f"[{agent.self_uid}] Single-agent segment advancing "
                    f"lookahead {lookahead} -> {lookahead + 1}"
                )
                io.set_lookahead(agent.self_uid, lookahead + 1)
            return False

        segment_key = getattr(agent, "current_segment_key", "unknown")
        frame_key = f"{segment_key}:{lookahead}"
        my_frame_sync = self._get_single_uav_state(io, agent.self_uid, "current_frame_sync")
        release_key, release_round = self._get_frame_release_info(agent, io)

        # Consume a latched release: every member advances together on the
        # round after the release was written.
        if (
            my_frame_sync == frame_key
            and release_key == frame_key
            and release_round is not None
            and release_round < current_round
        ):
            if lookahead < max_idx:
                io.set_lookahead(agent.self_uid, lookahead + 1)
                io.set_uav_state(agent.self_uid, "current_frame_sync", "")
                self.log(
                    f"[{agent.self_uid}] Consume frame release for {frame_key}, "
                    f"lookahead {lookahead} -> {lookahead + 1}"
                )
            else:
                self.log(
                    f"[{agent.self_uid}] Consume final-frame release for {frame_key}. "
                    f"Task completion will be recorded after this round's physics step."
                )
            return False

        # Still flying toward the current waypoint.
        if dist2target > CLOSE_TH_SYNC:
            return False

        # Arrived at the current waypoint; only mark arrival, do not fly yet.
        if my_frame_sync != frame_key:
            io.set_uav_state(agent.self_uid, "current_frame_sync", frame_key)
            self.log(
                f"[{agent.self_uid}] Arrived at frame {frame_key}. "
                f"Waiting for formation peers."
            )
            return True

        # All members of this segment must arrive at the same frame before the
        # release is latched.
        if not self._all_group_frame_arrived(agent, io, frame_key):
            return True

        if release_key != frame_key:
            self._set_frame_release_info(agent, io, frame_key, current_round)
            self.log(
                f"[{agent.self_uid}] All peers arrived at frame {frame_key}. "
                f"Release latched at round={current_round}."
            )
            return True

        self.log(
            f"[{agent.self_uid}] Frame release exists but is not consumable yet. "
            f"frame={frame_key}, release_round={release_round}, current_round={current_round}"
        )
        return True

    def _record_wait_state(
        self,
        agent,
        io,
        pos=None,
        target=None,
        current_round=None,
    ) -> None:
        if pos is None:
            me = io.get_pos(agent.self_uid, blue=True)
            if me:
                pos = [me["x"], me["y"], me["z"]]
            else:
                return

        f_type = getattr(agent, "formation_type", "unknown")
        s_ids = getattr(agent, "current_segment_siblings", [])
        lookahead = io.get_lookahead(agent.self_uid) or 0
        is_gathering = lookahead == 0 and not getattr(agent, "has_synced_segment", False)
        if is_gathering:
            f_type = "is_gathering"
            s_ids = []

        leader_id = self._get_leader_id(agent)
        segment_key = getattr(agent, "current_segment_key", None)
        agent.global_step_id += 1

        if hasattr(agent, "step_logs"):
            agent.step_logs.clear()

        extra_info = {
            "formation_type": f_type,
            "frame_id": None,
            "lookahead": lookahead,
            "global_id": agent.global_step_id,
            "segment_key": segment_key,
            "is_waiting": True,
            "waiting_reason": (
                "segment_start_barrier" if lookahead == 0 else "formation_frame_barrier"
            ),
            "flight_phase": "sync_wait",
            "leader_id": leader_id,
            "lookahead_coord": target if target else None,
            **agent.simulation_time_fields(round_id=current_round),
        }
        io.append_pos_traj_with_extra(agent.self_uid, pos, extra_info, blue=True)

    # ------------------------------------------------------------------
    # State and physics
    # ------------------------------------------------------------------
    def _get_agent_state(self, agent, io):
        me = io.get_pos(agent.self_uid, blue=True)
        if not me:
            return None

        traj = agent.cur_reference_traj
        if not traj:
            return None

        lookahead = io.get_lookahead(agent.self_uid)
        if lookahead is None:
            lookahead = 0

        max_idx = len(traj) - 1
        lookahead = max(0, min(lookahead, max_idx))
        target = traj[lookahead]
        self_pos = [me["x"], me["y"], me["z"]]
        dist_to_target = v_norm(v_sub(target, self_pos))
        self.log(
            f"[{agent.self_uid}] lookahead: {lookahead}, target: {target}, "
            f"dist_to_target: {dist_to_target}"
        )
        return me, traj, lookahead, max_idx, target, self_pos, dist_to_target

    def _check_task_completion(
        self,
        agent,
        io,
        lookahead,
        max_idx,
        dist_to_target,
    ) -> bool:
        if lookahead >= max_idx and dist_to_target <= CLOSE_TH_SYNC:
            seg_id = getattr(agent, "current_segment_id", None)
            if seg_id:
                io.set_flag(f"seg_done:{seg_id}", "1")

            if agent.is_final_task:
                agent.is_finished = True
                self.log(f"[{agent.self_uid}] Final task completed.")
            else:
                agent.waiting_next_segment = True
                agent.request_planning()
                self.log(f"[{agent.self_uid}] Segment completed. Waiting next.")

            agent.can_task_start = True
            return True
        return False

    def _calculate_physics(self, agent, io, target, self_pos):
        return bounded_motion_step(
            self_pos,
            target,
            dt=DT,
            max_horizontal_speed_mps=getattr(
                agent, "max_horizontal_speed_mps", MAX_HORIZONTAL_SPEED_MPS
            ),
            max_climb_rate_mps=getattr(agent, "max_climb_rate_mps", MAX_CLIMB_RATE_MPS),
            max_descent_rate_mps=getattr(agent, "max_descent_rate_mps", MAX_DESCENT_RATE_MPS),
        )

    def _update_status_and_redis(
        self,
        agent,
        io,
        nxt,
        lookahead,
        max_idx,
        dist_to_target,
        target=None,
        current_round=None,
    ) -> None:
        f_type = getattr(agent, "formation_type", "unknown")
        s_ids = getattr(agent, "current_segment_siblings", [])
        is_gathering = lookahead == 0 and not getattr(agent, "has_synced_segment", False)
        is_waiting = False
        waiting_reason = None
        flight_phase = "task_flight"
        if is_gathering:
            f_type = "unknown"
            waiting_reason = "flying_to_segment_start"
            flight_phase = "positioning"

        agent.global_step_id += 1
        self.log(
            f"[{agent.self_uid}] Step {agent.global_step_id}: "
            f"lookahead={lookahead}, dist_to_target={dist_to_target:.2f}, "
            f"is_waiting={is_waiting}, flight_phase={flight_phase}, round={current_round}"
        )

        if lookahead >= max_idx and dist_to_target <= CLOSE_TH_SYNC:
            segment_key = getattr(agent, "current_segment_key", "unknown")
            frame_key = f"{segment_key}:{lookahead}"
            group_ids = self._get_segment_group_ids(agent)
            if len(group_ids) <= 1:
                self._check_task_completion(
                    agent, io, lookahead, max_idx, dist_to_target
                )
            else:
                my_frame_sync = self._get_single_uav_state(
                    io, agent.self_uid, "current_frame_sync"
                )
                release_key, release_round = self._get_frame_release_info(agent, io)
                if (
                    my_frame_sync == frame_key
                    and release_key == frame_key
                    and release_round is not None
                    and release_round < current_round
                ):
                    self._check_task_completion(
                        agent, io, lookahead, max_idx, dist_to_target
                    )

        if hasattr(agent, "step_logs"):
            agent.step_logs.clear()

        release_key, release_round = self._get_segment_release_info(agent, io)
        extra_info = {
            "formation_type": f_type,
            "frame_id": lookahead,
            "lookahead": lookahead,
            "global_id": agent.global_step_id,
            "segment_key": getattr(agent, "current_segment_key", None),
            "is_waiting": is_waiting,
            "waiting_reason": waiting_reason,
            "flight_phase": flight_phase,
            "dist_to_target": dist_to_target,
            "leader_id": self._get_leader_id(agent),
            "lookahead_coord": target if target else None,
            "phase_state": {
                "has_synced_segment": getattr(agent, "has_synced_segment", False),
                "release_key": release_key,
                "release_round": release_round,
            },
            **agent.simulation_time_fields(round_id=current_round),
        }
        io.append_pos_traj_with_extra(agent.self_uid, nxt, extra_info, blue=True)

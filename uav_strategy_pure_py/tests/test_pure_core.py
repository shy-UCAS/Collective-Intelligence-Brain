import unittest

from uav_strategy_pure_py.behaviours import bounded_motion_step, SyncAPFStepEnhance
from uav_strategy_pure_py.memory_io import InMemoryUavIO


class PureCoreTests(unittest.TestCase):
    def test_bounded_motion_step_reaches_nearby_target(self):
        current = [0.0, 0.0, 0.0]
        target = [1.0, 2.0, 0.0]
        nxt = bounded_motion_step(current, target)
        self.assertEqual(nxt, target)

    def test_bounded_motion_step_limits_horizontal_step(self):
        current = [0.0, 0.0, 0.0]
        target = [1000.0, 0.0, 0.0]
        nxt = bounded_motion_step(current, target)
        self.assertLess(nxt[0], 1000.0)
        self.assertGreater(nxt[0], 0.0)

    def test_in_memory_io_append_is_native_list(self):
        io = InMemoryUavIO()
        io.add_uav_id("uav_1")
        io.set_lookahead("uav_1", 0)
        io.set_traj("uav_1", [[0.0, 0.0, 0.0]])
        io.append_traj_points("uav_1", [1.0, 1.0, 1.0])
        self.assertEqual(len(io.get_traj("uav_1")), 2)

    def test_behaviour_constructor_keeps_period_argument(self):
        behaviour = SyncAPFStepEnhance(period=0.5)
        self.assertEqual(behaviour.period, 0.5)


if __name__ == "__main__":
    unittest.main()

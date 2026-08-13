# -*- coding: utf-8 -*-
"""空域几何解析和局部地图投影的回归测试。"""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from airspace_map_viewer import (MapCanvas, _geom_center, extract_center,
                                 parse_geometry)


class GeometryParsingTests(unittest.TestCase):

    def test_geojson_polygon_uses_area_centroid_not_closed_vertex_average(self):
        geometry = {
            "type": "Polygon",
            "coordinates": [[[116, 39], [118, 39], [118, 41],
                             [116, 41], [116, 39]]],
        }
        self.assertEqual((117.0, 40.0), _geom_center(geometry))

    def test_wkt_polygon_with_double_parentheses_is_parsed(self):
        geometry = "POLYGON((116 39,118 39,118 41,116 41,116 39))"
        self.assertEqual((117.0, 40.0), _geom_center(geometry))

    def test_geojson_feature_collection_and_multipolygon_are_supported(self):
        geometry = {
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "geometry": {
                    "type": "MultiPolygon",
                    "coordinates": [
                        [[[116, 39], [117, 39], [117, 40],
                          [116, 40], [116, 39]]],
                    ],
                },
            }],
        }
        parsed = parse_geometry(geometry)
        self.assertEqual(1, len(parsed["polygons"]))
        self.assertEqual((116.5, 39.5), _geom_center(geometry))

    def test_facility_zero_coordinate_is_not_treated_as_missing(self):
        record = {"facilityList": [{"lng": 0, "lat": 0}]}
        self.assertEqual((0.0, 0.0, "facility"), extract_center(record))

    def test_center_uses_first_facility_not_facility_centroid(self):
        # 三级半径圆心规则: facilityList 第一个设施, 而非设施质心。
        record = {"facilityList": [
            {"lng": 116.1, "lat": 39.1},
            {"lng": 116.9, "lat": 39.9},
        ]}
        self.assertEqual((116.1, 39.1, "facility"), extract_center(record))


class ProjectionTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_north_has_positive_local_y_offset(self):
        canvas = MapCanvas()
        canvas.set_record({
            "zoneType": 1,
            "warningRadius": 1000,
            "facilityList": [{"lng": 116.4, "lat": 39.9}],
        })
        _, north = canvas._offset_m(116.4, 40.0)
        self.assertGreater(north, 0)


if __name__ == "__main__":
    unittest.main()

# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import unittest
from agent import extract_surface_id

class SurfaceIdExtractionTest(unittest.TestCase):

  def test_extract_from_create_surface(self):
    data = {"createSurface": {"surfaceId": "map_surface_1", "catalogId": "maps"}}
    self.assertEqual(extract_surface_id(data), "map_surface_1")

  def test_extract_from_update_components(self):
    data = {"updateComponents": {"surfaceId": "details_card_2", "components": []}}
    self.assertEqual(extract_surface_id(data), "details_card_2")

  def test_extract_from_update_data_model(self):
    data = {"updateDataModel": {"surfaceId": "weather_card_3", "dataModel": {}}}
    self.assertEqual(extract_surface_id(data), "weather_card_3")

  def test_extract_from_delete_surface(self):
    data = {"deleteSurface": {"surfaceId": "old_surface_4"}}
    self.assertEqual(extract_surface_id(data), "old_surface_4")

  def test_extract_non_matching_or_malformed_data(self):
    self.assertIsNone(extract_surface_id({"text": "hello"}))
    self.assertIsNone(extract_surface_id(None))
    self.assertIsNone(extract_surface_id("not_a_dict"))
    self.assertIsNone(extract_surface_id({"createSurface": "malformed_shape"}))
    self.assertIsNone(extract_surface_id({"createSurface": {}}))

if __name__ == '__main__':
  unittest.main()

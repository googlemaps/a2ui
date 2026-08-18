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

"""Tests for Router Configuration."""

import unittest
from python_agent.router_config import IntentClass
from python_agent.router_config import ROUTER_SYSTEM_INSTRUCTION
from python_agent.router_config import RouterClassification


class TestRouterConfig(unittest.TestCase):
  """Unit tests for Intent Router configuration schema and prompt."""

  def test_schema_instantiation(self):
    data = {"intent": "LOCAL_SEARCH", "query": "coffee near me"}
    classification = RouterClassification(**data)
    self.assertEqual(classification.intent, IntentClass.LOCAL_SEARCH)
    self.assertEqual(classification.query, "coffee near me")

  def test_schema_validation_error(self):
    data = {"intent": "INVALID_INTENT", "query": "coffee near me"}
    with self.assertRaises(ValueError):
      RouterClassification(**data)

  def test_instruction_not_empty(self):
    self.assertGreater(len(ROUTER_SYSTEM_INSTRUCTION), 0)


if __name__ == "__main__":
  unittest.main()

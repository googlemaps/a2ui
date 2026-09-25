# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Selects (or creates) an iPhone simulator for the active Xcode.

Picks the newest installed iOS runtime that the active Xcode can target, i.e.
whose major version is at most the major version of the active Xcode's iOS
Simulator SDK. Runner images can have runtimes installed for other (newer)
Xcodes, which the active Xcode rejects as a test destination.

Used by .github/workflows/ios-ci.yml. On success, prints only the simulator
UDID to stdout; all diagnostics go to stderr.

Exit codes:
  0: Success; UDID printed to stdout.
  1: An `xcrun` invocation failed.
  2: No available iOS Simulator runtime usable by the active Xcode is installed.
  3: The selected iOS runtime has no iPhone device type to create a simulator.
  4: Unexpected error (e.g. malformed `simctl` output); traceback on stderr.
"""

import json
import subprocess
import sys
import traceback

# Preferred model, so the test device stays stable across runner image updates
# as long as the runtime supports it. Falls back to any iPhone otherwise.
PREFERRED_DEVICE_NAME = "iPhone 16"

EXIT_XCRUN_FAILED = 1
EXIT_NO_RUNTIME = 2
EXIT_NO_IPHONE_TYPE = 3
EXIT_UNEXPECTED = 4


def log(message):
  print(message, file=sys.stderr)


def xcrun(*args):
  """Runs `xcrun <args>` and returns stdout, exiting 1 on failure."""
  cmd = ["xcrun", *args]
  try:
    return subprocess.run(
        cmd, check=True, capture_output=True, text=True
    ).stdout
  except subprocess.CalledProcessError as e:
    log(f"`{' '.join(cmd)}` failed with exit code {e.returncode}:")
    log(e.stderr)
    sys.exit(EXIT_XCRUN_FAILED)


def simctl(*args):
  """Runs `xcrun simctl <args>` and returns stdout, exiting 1 on failure."""
  return xcrun("simctl", *args)


def version_key(version):
  # Non-numeric components (e.g. "0b1" in a beta runtime) sort as 0. Beta
  # runtimes are not expected on GitHub-hosted runners.
  return tuple(int(p) if p.isdigit() else 0 for p in version.split("."))


def is_ios_runtime(runtime):
  return runtime.get("isAvailable") and (
      runtime.get("platform") == "iOS"
      or runtime.get("name", "").startswith("iOS")
  )


def pick_existing_device(devices):
  """Returns the preferred available iPhone, else any available iPhone."""
  iphones = [
      d
      for d in devices
      if d.get("isAvailable") and d.get("name", "").startswith("iPhone")
  ]
  for device in iphones:
    if device.get("name") == PREFERRED_DEVICE_NAME:
      return device
  return iphones[0] if iphones else None


def pick_device_type(runtime):
  """Returns the preferred iPhone device type, else the last listed one."""
  iphones = [
      dt
      for dt in runtime.get("supportedDeviceTypes", [])
      if dt.get("productFamily") == "iPhone"
  ]
  for device_type in iphones:
    if device_type.get("name") == PREFERRED_DEVICE_NAME:
      return device_type
  # simctl lists device types oldest-first in practice (not documented), so
  # the last entry is normally the newest iPhone model.
  return iphones[-1] if iphones else None


def main():
  sdk_version = xcrun("--sdk", "iphonesimulator", "--show-sdk-version").strip()
  max_major = version_key(sdk_version)[0]
  log(f"Active Xcode iOS Simulator SDK: {sdk_version}")

  data = json.loads(simctl("list", "-j"))
  runtimes = sorted(
      (
          r
          for r in data.get("runtimes", [])
          if is_ios_runtime(r)
          and version_key(r.get("version", "0"))[0] <= max_major
      ),
      key=lambda r: version_key(r.get("version", "0")),
      reverse=True,
  )
  if not runtimes:
    log(
        "No available iOS Simulator runtime usable by the active Xcode"
        f" (iOS {max_major} or older) is installed."
    )
    return EXIT_NO_RUNTIME
  runtime = runtimes[0]

  device = pick_existing_device(
      data.get("devices", {}).get(runtime["identifier"], [])
  )
  if device:
    log(f"Selected {device['name']} on {runtime['name']}")
    print(device["udid"])
    return 0

  device_type = pick_device_type(runtime)
  if not device_type:
    log(f"{runtime['name']} has no supported iPhone device type.")
    return EXIT_NO_IPHONE_TYPE
  log(
      f"Creating {device_type.get('name', device_type['identifier'])} on"
      f" {runtime['name']}"
  )
  print(
      simctl(
          "create",
          "CI-iPhone",
          device_type["identifier"],
          runtime["identifier"],
      ).strip()
  )
  return 0


if __name__ == "__main__":
  try:
    sys.exit(main())
  except Exception:  # pylint: disable=broad-exception-caught
    traceback.print_exc()
    sys.exit(EXIT_UNEXPECTED)

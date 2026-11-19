#
# Copyright (c) 2026 TQ-Systems GmbH <license@tq-group.com>, D-82229 Seefeld, Germany. All rights reserved.
# Author: Hans-Christian Melzer and the Energy Manager development team
#
# This software is licensed under the TQ-Systems Product Software License Agreement Version 1.0.3 or any later version.
# You can obtain a copy of the License Agreement in the TQS (TQ-Systems Software Licenses) folder on the following website:
# https://www.tq-group.com/en/support/downloads/tq-software-license-conditions/
# In case of any license issues please contact license@tq-group.com.
#
"""Writes the licenses of the go-licenses manifest into the Go SBOM of an app.

cyclonedx-gomod has its own license detection, but it misreads several modules and does not
know the TQ licenses. The manifest of em-go-licenses is what the package ships, so the SBOM
takes its licenses from there.

The manifest lists packages, the SBOM lists modules. Each package belongs to the module with
the longest matching path. A module without a known license gets NOASSERTION.
"""
import argparse
import json
import sys

from cyclonedx.spdx import is_expression, is_supported_id

NOASSERTION = "NOASSERTION"


def read_manifest(text):
    """Returns (name, license) pairs of a manifest written with /etc/manifest.tpl."""
    entries, entry = [], {}
    for line in text.splitlines() + [""]:
        key, _, value = line.partition(":")
        if key.strip():
            entry[key.strip()] = value.strip()
        elif entry:
            entries.append((entry.get("name", ""), entry.get("license", "")))
            entry = {}
    return entries


def owning_module(package, modules):
    """Returns the module with the longest path that contains the package, or None."""
    matches = [m for m in modules if package == m or package.startswith(m + "/")]
    return max(matches, key=len, default=None)


def license_entries(names):
    """Returns the CycloneDX licenses of a component, with id for SPDX identifiers.

    An expression such as "MIT OR Apache-2.0" has to stand alone, the schema takes either a list
    of licenses or exactly one expression. A name that is neither stays a plain name.
    """
    if len(names) == 1 and not is_supported_id(names[0]) and is_expression(names[0]):
        return [{"expression": names[0]}]
    return [{"license": {"id" if is_supported_id(name) else "name": name}} for name in names]


def add_licenses(sbom, manifest_entries):
    """Sets the licenses of the main module and of every module component of the SBOM.

    Returns the sorted names of the modules without a known license.
    """
    components = [sbom["metadata"]["component"]] + sbom.get("components", [])
    found = {c["name"]: set() for c in components}
    for package, name in manifest_entries:
        module = owning_module(package, found)
        if module and name and name != "Unknown":
            found[module].add(name)
    for component in components:
        names = sorted(found[component["name"]]) or [NOASSERTION]
        component["licenses"] = license_entries(names)
    return sorted(c["name"] for c in components if not found[c["name"]])


def main(argv=None):
    """Adds the licenses to the SBOM file in place."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("sbom", help="Go SBOM written by cyclonedx-gomod, changed in place")
    parser.add_argument("manifest", help="manifest written by em-go-licenses report")
    args = parser.parse_args(argv)
    try:
        with open(args.sbom, encoding="utf-8") as file:
            sbom = json.load(file)
        with open(args.manifest, encoding="utf-8") as file:
            entries = read_manifest(file.read())
        unknown = add_licenses(sbom, entries)
        with open(args.sbom, "w", encoding="utf-8") as file:
            json.dump(sbom, file, indent=2)
    except (OSError, ValueError) as exc:
        sys.exit(f"error: {exc}")
    if unknown:
        print(f"warning: {args.sbom}: no license for {', '.join(unknown)}", file=sys.stderr)

#
# Copyright (c) 2026 TQ-Systems GmbH <license@tq-group.com>, D-82229 Seefeld, Germany. All rights reserved.
# Author: Hans-Christian Melzer and the Energy Manager development team
#
# This software is licensed under the TQ-Systems Product Software License Agreement Version 1.0.3 or any later version.
# You can obtain a copy of the License Agreement in the TQS (TQ-Systems Software Licenses) folder on the following website:
# https://www.tq-group.com/en/support/downloads/tq-software-license-conditions/
# In case of any license issues please contact license@tq-group.com.
#
"""Merges the SBOMs of the apps of a RAUC bundle and the SBOM of the core image into one
CycloneDX file per bundle, with the layers bundle, apps and operating system.

The tool creates no SBOM itself. The bundle names the apps it installs, their SBOMs come from the
directory that tqem-fetch-app-sboms filled from the deploy tree, and the core image SBOM from the
command line.
"""
import argparse
import configparser
import datetime
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
import tarfile
import uuid

from cyclonedx.schema import SchemaVersion
from cyclonedx.validation.json import JsonStrictValidator
from packageurl import PackageURL

from tqem import bundle
from tqem.app_sboms import read_app_sboms

SPEC_VERSION = "1.6"
ROOT_COMPONENT_NAME = "EM Bundle"
TOOL_NAME = "tqem-bundle-sbom"
ROOT_BOM_REF = "em-bundle-root"
APP_PURL_PREFIX = "pkg:emos-app/"
OS_BOM_REF = "pkg:emos-os/core-image"
MERGED_COMPONENT_FIELDS = (
    "type", "group", "cpe", "name", "version", "purl", "licenses", "properties")
CPE_PART_TYPES = {"a": "generic", "o": "os", "h": "hardware"}


class SbomError(Exception):
    """An error that aborts the run with a message instead of a traceback."""


def cpe_to_purl(cpe, version):
    """Converts a CPE 2.3 string to a package URL."""
    parts = cpe.split(":")
    if len(parts) < 5 or parts[0] != "cpe" or parts[1] != "2.3":
        raise ValueError(f"invalid CPE {cpe}")
    vendor, product = parts[3], parts[4]
    purl_type = CPE_PART_TYPES.get(parts[2], "generic")
    namespace = vendor if vendor != product else None
    return str(PackageURL(type=purl_type, namespace=namespace, name=product, version=version))


def missing_purl(component):
    """Derives a package URL for a component without one, from its CPE or its type and name."""
    if component.get("cpe"):
        try:
            return cpe_to_purl(component["cpe"], component.get("version"))
        except ValueError as exc:
            print(f"warning: {exc}", file=sys.stderr)
            return None
    return str(PackageURL(type=component.get("type"), name=component.get("name"),
                          version=component.get("version")))


class BundleSbom:
    """Builds the merged SBOM. The purl of a component doubles as its bom-ref."""

    def __init__(self, exclude_purls):
        self.exclude_purls = exclude_purls
        self.components = []
        self.dependencies = []
        self.root_refs = []
        self.seen_purls = set()

    def add_layer(self, layer, sbom_docs):
        """Adds a layer component (app or operating system) and the components of its SBOMs."""
        self.components.append(layer)
        self.root_refs.append(layer["bom-ref"])
        refs = []
        for doc in sbom_docs:
            for source in doc.get("components", []):
                component = {key: source[key] for key in MERGED_COMPONENT_FIELDS if key in source}
                if "purl" not in component:
                    purl = missing_purl(component)
                    if purl:
                        component["purl"] = purl
                purl = component.get("purl")
                if purl and any(text in purl for text in self.exclude_purls):
                    continue
                if purl:
                    component["bom-ref"] = purl
                    if purl not in refs:
                        refs.append(purl)
                    if purl in self.seen_purls:
                        continue
                    self.seen_purls.add(purl)
                self.components.append(component)
        if refs:
            self.dependencies.append({"ref": layer["bom-ref"], "dependsOn": refs})

    def document(self):
        """Returns the merged CycloneDX document."""
        return {
            "bomFormat": "CycloneDX",
            "specVersion": SPEC_VERSION,
            "version": 1,
            "metadata": {
                "component": {
                    "type": "firmware", "name": ROOT_COMPONENT_NAME, "bom-ref": ROOT_BOM_REF}
            },
            "components": self.components,
            "dependencies": [{"ref": ROOT_BOM_REF, "dependsOn": self.root_refs}]
            + self.dependencies,
        }


def merge(app_sboms, core_sbom, exclude_purls=()):
    """Merges the app SBOMs and the core image SBOM.

    Args:
        app_sboms (dict): app name -> list of SBOM documents, an empty list marks a gap
        core_sbom (dict): SBOM document of the core image
        exclude_purls (iterable): components whose purl contains one of these texts are dropped

    Returns:
        tuple: (merged document, sorted names of the apps without SBOM)
    """
    bundle_sbom = BundleSbom(tuple(exclude_purls))
    for app in sorted(name for name, docs in app_sboms.items() if docs):
        docs = app_sboms[app]
        layer = {"type": "application", "name": app,
                 "bom-ref": APP_PURL_PREFIX + app, "purl": APP_PURL_PREFIX + app}
        # The frontend SBOM of an app carries no version, the backend SBOM does
        version = next((doc["metadata"]["component"]["version"] for doc in docs
                        if doc.get("metadata", {}).get("component", {}).get("version")), None)
        if version:
            layer["version"] = version
        bundle_sbom.add_layer(layer, docs)
    bundle_sbom.add_layer({"type": "operating-system", "name": "core-image",
                           "bom-ref": OS_BOM_REF, "purl": OS_BOM_REF}, [core_sbom])
    return bundle_sbom.document(), sorted(name for name, docs in app_sboms.items() if not docs)


def add_metadata(sbom, bundle_name, version, compatible, missing_apps):
    """Fills the CycloneDX metadata and keeps the EMOS specific values as properties.

    The root component carries the BUNDLE_NAME of the bundle Makefile, e.g. "embase EM Bundle",
    and the bundle version.
    """
    sbom["serialNumber"] = f"urn:uuid:{uuid.uuid4()}"
    metadata = sbom["metadata"]
    metadata["component"]["name"] = f"{bundle_name} {ROOT_COMPONENT_NAME}"
    metadata["timestamp"] = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")
    metadata["tools"] = {"components": [{"type": "application", "name": TOOL_NAME,
                                         "version": importlib.metadata.version("tqem")}]}
    if version:
        metadata["component"]["version"] = version
    properties = {"emos.compatible": compatible, "emos.apps_without_sbom": ",".join(missing_apps)}
    sbom["properties"] = [{"name": name, "value": value}
                          for name, value in properties.items() if value]


def validate(sbom):
    """Raises SbomError if the document is not valid CycloneDX 1.6."""
    errors = JsonStrictValidator(SchemaVersion.V1_6).validate_str(json.dumps(sbom))
    if errors:
        raise SbomError(f"merged SBOM is not valid CycloneDX {SPEC_VERSION}: {errors!r}")


def report(sbom, missing_apps, output_file):
    """Prints a summary and the findings that need a look."""
    components = sbom["components"]
    print(f"{output_file}: {len(components)} components")
    if missing_apps:
        print(f"warning: apps without SBOM: {', '.join(missing_apps)}", file=sys.stderr)
    for label, matches in (
            ("components without purl", [c for c in components if "purl" not in c]),
            ("components with version UNKNOWN",
             [c for c in components if c.get("version") == "UNKNOWN"])):
        if matches:
            names = ", ".join(c.get("name", "?") for c in matches)
            print(f"warning: {label}: {names}", file=sys.stderr)


def main(argv=None):
    """Writes one merged SBOM per bundle in the bundle directory."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-dir", required=True, help="directory with the .raucb files")
    parser.add_argument("--bundle-name", required=True, help="BUNDLE_NAME of the bundle Makefile")
    parser.add_argument("--app-sbom-dir", required=True,
                        help="directory with one directory of SBOMs per app, see "
                             "tqem-fetch-app-sboms")
    parser.add_argument("--core-image-sbom", required=True, help="CycloneDX SBOM of the core image")
    parser.add_argument("--output-dir", required=True, help="directory for <bundle>-sbom.json")
    parser.add_argument("--work-dir", required=True, help="scratch directory, emptied per bundle")
    parser.add_argument("--exclude-purl", action="append", default=[], metavar="TEXT",
                        help="drop components whose purl contains TEXT (repeatable)")
    args = parser.parse_args(argv)

    try:
        for name in ("bundle_dir", "bundle_name", "app_sbom_dir", "core_image_sbom", "output_dir",
                     "work_dir"):
            if not getattr(args, name):
                raise SbomError(f"--{name.replace('_', '-')} is empty")
        bundles = sorted(n for n in os.listdir(args.bundle_dir) if n.endswith(".raucb"))
        if not bundles:
            raise SbomError(f"no .raucb file in {args.bundle_dir}")
        if not os.path.isdir(args.app_sbom_dir):
            raise SbomError(f"app SBOM directory not found: {args.app_sbom_dir}")
        with open(args.core_image_sbom, encoding="utf-8") as core_file:
            core_sbom = json.load(core_file)

        os.makedirs(args.output_dir, exist_ok=True)
        for raucb in bundles:
            write_bundle_sbom(args, raucb, core_sbom)
    except (SbomError, OSError, ValueError, configparser.Error, tarfile.TarError,
            subprocess.CalledProcessError) as exc:
        sys.exit(f"error: {exc}")


def write_bundle_sbom(args, raucb, core_sbom):
    """Writes the merged SBOM of one bundle file to the output directory.

    The bundle names the apps it installs, the SBOMs of those apps come from the download
    directory. An app whose SBOM is missing there ends up in emos.apps_without_sbom.
    """
    bundle_file = os.path.splitext(raucb)[0]
    work_dir = os.path.join(args.work_dir, bundle_file)
    shutil.rmtree(work_dir, ignore_errors=True)
    os.makedirs(work_dir)
    manifest, apps = bundle.extract_bundle(os.path.join(args.bundle_dir, raucb), work_dir)
    sbom, missing_apps = merge(read_app_sboms(args.app_sbom_dir, apps), core_sbom,
                               args.exclude_purl)
    add_metadata(sbom, args.bundle_name,
                 manifest.get("update", "version", fallback=None),
                 manifest.get("update", "compatible", fallback=None), missing_apps)
    validate(sbom)
    output_file = os.path.join(args.output_dir, bundle_file + "-sbom.json")
    with open(output_file, "w", encoding="utf-8") as output:
        json.dump(sbom, output, indent=4)
    report(sbom, missing_apps, output_file)

#
# Copyright (c) 2026 TQ-Systems GmbH <license@tq-group.com>, D-82229 Seefeld, Germany. All rights reserved.
# Author: Hans-Christian Melzer and the Energy Manager development team
#
# This software is licensed under the TQ-Systems Product Software License Agreement Version 1.0.3 or any later version.
# You can obtain a copy of the License Agreement in the TQS (TQ-Systems Software Licenses) folder on the following website:
# https://www.tq-group.com/en/support/downloads/tq-software-license-conditions/
# In case of any license issues please contact license@tq-group.com.
#
"""Collects the SBOMs of the apps of a bundle into one directory per app.

Apps deploy their SBOM below doc/ instead of shipping it inside the package, so the bundle build
has to collect it. The module reads the same bundle specs as emit and derives the doc folder of
every app from the package URL of the spec. The fileserver publishes the deploy tree, therefore
that URL also names the path below the tree mounted at TQEM_BASE_DEPLOY_PATH, and the SBOMs are
copied from there. An app whose SBOM is missing keeps an empty directory, tqem-bundle-sbom reports
it as an app without SBOM.
"""
import argparse
import json
import os
import pathlib
import re
import shutil
import sys
import urllib.parse

import yaml

# Every app writes its SBOMs below doc/ under the package name, one per build system
SBOM_SUFFIXES = ("go-sbom.json", "frontend-sbom.json")
BIN_DIRNAME = "bin"
DOC_DIRNAME = "doc"
SBOM_SUFFIX = "bom.json"
BASE_DEPLOY_PATH_ENV = "TQEM_BASE_DEPLOY_PATH"
ENV_MATCHER = re.compile(r"\$\{([^}]+)\}|\$([A-Za-z_][A-Za-z0-9_]*)")


class AppSbomError(Exception):
    """An error that aborts the run with a message instead of a traceback."""


def expand_env(value):
    """Replaces ${VAR} and $VAR with the environment value, like emit does while loading."""
    return ENV_MATCHER.sub(lambda match: os.environ.get(match.group(1) or match.group(2), ""),
                           value)


def merge_dicts(base, extra):
    """Merges extra into base, nested dictionaries key by key, like emit does with its specs."""
    merged = dict(base)
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged


def read_specs(paths):
    """Returns the merged defaults and apps of the bundle specs, in the given order."""
    spec = {}
    for path in paths:
        with open(path, encoding="utf-8") as spec_file:
            try:
                spec = merge_dicts(spec, yaml.safe_load(spec_file) or {})
            except yaml.YAMLError as exc:
                raise AppSbomError(f"{path}: {exc}") from exc
    return spec.get("defaults", {}), spec.get("apps", {})


def app_name(app, app_info):
    """Returns the package name of an app, the same rule emit uses for its download URL.

    The optional key name replaces it, otherwise a variant extends it. The name is what the app
    build writes into its SBOM filenames.
    """
    if "name" in app_info:
        return app_info["name"]
    if "variant" in app_info:
        return f"{app}-{app_info['variant']}"
    return app


def doc_path(app, name, app_info, base_deploy_path):
    """Returns the doc folder of an app in the deploy tree, derived from its package URL.

    A web URL names the path below base_deploy_path, the fileserver publishes exactly that tree.
    A file URL already is the path on disk. The doc folder lies in the deploy folder of the
    package, next to bin, so a field of the package name, such as arch, may stay without value.
    """
    if not app_info.get("url"):
        raise AppSbomError(f"no url in the spec for app {app}")
    fields = merge_dicts(app_info, {"app": app, "name": name})
    # emit expands the environment while loading, so a ${VAR} of the URL resolves before its fields
    template = expand_env(app_info["url"]).rsplit("/", 1)[0]
    try:
        url = expand_env(template.format(**fields))
    except KeyError as exc:
        raise AppSbomError(f"no value for {exc} in the URL of app {app}") from exc
    parts = urllib.parse.urlsplit(url)
    directory = pathlib.PurePosixPath(urllib.parse.unquote(parts.path))
    if directory.name == BIN_DIRNAME:
        directory = directory.parent
    if parts.scheme in ("http", "https"):
        return pathlib.Path(base_deploy_path, str(directory).lstrip("/"), DOC_DIRNAME)
    return pathlib.Path(directory, DOC_DIRNAME)


def fetch_app(app, app_info, output_dir, base_deploy_path):
    """Copies the SBOMs of one app out of the deploy tree. Returns the number of files."""
    name = app_name(app, app_info)
    doc_dir = doc_path(app, name, app_info, base_deploy_path)
    app_dir = pathlib.Path(output_dir, app)
    app_dir.mkdir(parents=True, exist_ok=True)
    found = 0
    for suffix in SBOM_SUFFIXES:
        sbom_file = doc_dir / f"{name}.{suffix}"
        if sbom_file.is_file():
            shutil.copy(sbom_file, app_dir)
            found += 1
    return found


def fetch_apps(defaults, apps, output_dir, base_deploy_path):
    """Collects the SBOMs of every app of the bundle.

    Returns:
        tuple: (number of apps with at least one SBOM, sorted names of the apps without one)
    """
    fetched, missing = 0, []
    for app in sorted(apps):
        info = apps[app]
        # An app set to null in a later spec is not part of the bundle
        if info is None:
            continue
        if fetch_app(app, merge_dicts(defaults, info), output_dir, base_deploy_path):
            fetched += 1
        else:
            missing.append(app)
    return fetched, missing


def read_app_sboms(app_sbom_dir, apps):
    """Collects the SBOMs of the given apps out of the output directory, one entry per app.

    The apps are the ones a bundle installs, the directory holds the files of every app of the
    specs. An app without SBOM stays in the result with an empty list, it marks a gap.
    """
    app_sboms = {}
    for app in sorted(apps):
        app_path = pathlib.Path(app_sbom_dir, app)
        app_sboms[app] = [json.loads(sbom_file.read_text(encoding="utf-8"))
                          for sbom_file in sorted(app_path.glob("*" + SBOM_SUFFIX))]
    return app_sboms


def main(argv=None):
    """Fills the output directory with one directory of SBOMs per app."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-spec", required=True, action="append", metavar="FILE",
                        help="bundle spec, repeatable in the order emit reads them")
    parser.add_argument("--output-dir", required=True, help="directory for the app directories")
    args = parser.parse_args(argv)

    try:
        if not args.output_dir:
            raise AppSbomError("--output-dir is empty")
        base_deploy_path = os.environ.get(BASE_DEPLOY_PATH_ENV)
        if not base_deploy_path:
            raise AppSbomError(f"{BASE_DEPLOY_PATH_ENV} is not set, it names the root of the "
                               "mounted deploy tree")
        os.makedirs(args.output_dir, exist_ok=True)
        defaults, apps = read_specs(args.bundle_spec)
        fetched, missing = fetch_apps(defaults, apps, args.output_dir, base_deploy_path)
        print(f"{args.output_dir}: SBOMs of {fetched} apps")
        if missing:
            print(f"warning: no SBOM below doc for: {', '.join(missing)}", file=sys.stderr)
    except (AppSbomError, OSError) as exc:
        sys.exit(f"error: {exc}")

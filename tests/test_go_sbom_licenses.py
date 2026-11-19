#
# Copyright (c) 2026 TQ-Systems GmbH <license@tq-group.com>, D-82229 Seefeld, Germany. All rights reserved.
# Author: Hans-Christian Melzer and the Energy Manager development team
#
# This software is licensed under the TQ-Systems Product Software License Agreement Version 1.0.3 or any later version.
# You can obtain a copy of the License Agreement in the TQS (TQ-Systems Software Licenses) folder on the following website:
# https://www.tq-group.com/en/support/downloads/tq-software-license-conditions/
# In case of any license issues please contact license@tq-group.com.
#
"""Tests of tqem.go_sbom_licenses with a manifest and SBOM like in a build."""
# pylint: disable=missing-function-docstring
import json
import pathlib
import subprocess
import sys

import pytest

from tqem import go_sbom_licenses

MANIFEST = """
name:     example.com/app/backend/v2
version:  Unknown
license:  TQSSLAv1.0.4

name:     golang.org/x/sys/unix
version:  Unknown
license:  BSD-3-Clause

name:     example.com/lib.git/contract
version:  Unknown
license:  MIT

name:     example.com/lib.git/v2/contract
version:  Unknown
license:  TQSSLAv1.0.4

name:     example.com/mystery
version:  Unknown
license:  Unknown

"""


def go_sbom(*modules):
    """Returns a Go SBOM of the main module example.com/app/backend/v2 and the given modules."""
    return {"metadata": {"component": {"name": "example.com/app/backend/v2"}},
            "components": [{"name": m} for m in modules]}


def licenses(sbom):
    """Returns module -> license entries."""
    return {c["name"]: c["licenses"]
            for c in [sbom["metadata"]["component"]] + sbom["components"]}


def test_manifest_entries():
    assert go_sbom_licenses.read_manifest(MANIFEST)[:2] == [
        ("example.com/app/backend/v2", "TQSSLAv1.0.4"), ("golang.org/x/sys/unix", "BSD-3-Clause")]


def test_package_belongs_to_longest_module():
    sbom = go_sbom("golang.org/x/sys", "example.com/lib.git", "example.com/lib.git/v2")
    go_sbom_licenses.add_licenses(sbom, go_sbom_licenses.read_manifest(MANIFEST))
    assert licenses(sbom) == {
        "example.com/app/backend/v2": [{"license": {"name": "TQSSLAv1.0.4"}}],
        "golang.org/x/sys": [{"license": {"id": "BSD-3-Clause"}}],
        "example.com/lib.git": [{"license": {"id": "MIT"}}],
        "example.com/lib.git/v2": [{"license": {"name": "TQSSLAv1.0.4"}}],
    }


def test_compound_license_becomes_an_expression():
    sbom = go_sbom("example.com/dual")
    go_sbom_licenses.add_licenses(sbom, [("example.com/dual", "MIT OR Apache-2.0")])
    assert licenses(sbom)["example.com/dual"] == [{"expression": "MIT OR Apache-2.0"}]


@pytest.mark.parametrize("module", ["example.com/mystery", "example.com/missing"])
def test_module_without_license_gets_noassertion(module):
    sbom = go_sbom(module)
    unknown = go_sbom_licenses.add_licenses(sbom, go_sbom_licenses.read_manifest(MANIFEST))
    assert licenses(sbom)[module] == [{"license": {"name": "NOASSERTION"}}]
    assert unknown == [module]


def test_prefix_without_slash_is_no_match():
    assert go_sbom_licenses.owning_module("example.com/libfoo", {"example.com/lib"}) is None


def test_executable_writes_the_licenses_into_the_sbom(tmp_path):
    sbom_file = tmp_path / "app.go-sbom.json"
    sbom_file.write_text(json.dumps(go_sbom("golang.org/x/sys")))
    manifest_file = tmp_path / "app.golang.manifest"
    manifest_file.write_text(MANIFEST)
    # pip installs the executable next to the interpreter of the venv
    executable = pathlib.Path(sys.executable).parent / "tqem-go-sbom-licenses"

    subprocess.run([executable, sbom_file, manifest_file], check=True)

    assert licenses(json.loads(sbom_file.read_text()))["golang.org/x/sys"] == [
        {"license": {"id": "BSD-3-Clause"}}]


def test_missing_manifest_aborts(tmp_path):
    sbom_file = tmp_path / "app.go-sbom.json"
    sbom_file.write_text(json.dumps(go_sbom("golang.org/x/sys")))

    with pytest.raises(SystemExit, match="error: .*app.golang.manifest"):
        go_sbom_licenses.main([str(sbom_file), str(tmp_path / "app.golang.manifest")])


def test_unknown_license_is_warned_on_stderr(tmp_path, capsys):
    sbom_file = tmp_path / "app.go-sbom.json"
    sbom_file.write_text(json.dumps(go_sbom("example.com/missing")))
    manifest_file = tmp_path / "app.golang.manifest"
    manifest_file.write_text(MANIFEST)

    go_sbom_licenses.main([str(sbom_file), str(manifest_file)])

    assert "no license for example.com/missing" in capsys.readouterr().err

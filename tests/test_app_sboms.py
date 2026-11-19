#
# Copyright (c) 2026 TQ-Systems GmbH <license@tq-group.com>, D-82229 Seefeld, Germany. All rights reserved.
# Author: Hans-Christian Melzer and the Energy Manager development team
#
# This software is licensed under the TQ-Systems Product Software License Agreement Version 1.0.3 or any later version.
# You can obtain a copy of the License Agreement in the TQS (TQ-Systems Software Licenses) folder on the following website:
# https://www.tq-group.com/en/support/downloads/tq-software-license-conditions/
# In case of any license issues please contact license@tq-group.com.
#
"""Tests of tqem.app_sboms against a deploy tree below tmp_path."""
# pylint: disable=missing-function-docstring
import json
import pathlib

import pytest

from tqem import app_sboms

URL = "http://files.example.com/snapshots/apps/{app}/{branch}/{name}_{version}_{arch}.empkg"
BASE_SPEC = """
defaults:
  url: http://files.example.com/snapshots/apps/{app}/{branch}/{name}_{version}_{arch}.empkg
  branch: main
  arch: aarch64
  version: latest
apps:
  backup:
    version: 'latest'
  presets:
    variant: 'tq-embase'
"""
BUNDLE_SPEC = """
apps:
  backup: null
  device-settings:
    name: 'device-settings-baseline'
    branch: 'release'
"""


def write_specs(tmp_path):
    """Writes both specs and returns their paths in the order emit reads them."""
    paths = []
    for name, content in (("base.yml", BASE_SPEC), ("bundle.yml", BUNDLE_SPEC)):
        path = tmp_path / name
        path.write_text(content)
        paths.append(str(path))
    return paths


def test_specs_merge_like_emit(tmp_path):
    defaults, apps = app_sboms.read_specs(write_specs(tmp_path))

    assert defaults == {"url": URL, "branch": "main", "arch": "aarch64",
                        "version": "latest"}
    assert apps["backup"] is None
    assert apps["device-settings"]["branch"] == "release"
    assert apps["presets"]["variant"] == "tq-embase"


def test_path_follows_the_package_name():
    cases = [
        ("backup", {"branch": "main"}, "backup", "snapshots/apps/backup/main/doc"),
        ("presets", {"branch": "main", "variant": "tq-embase"}, "presets-tq-embase",
         "snapshots/apps/presets/main/doc"),
        ("device-settings", {"branch": "release", "name": "device-settings-baseline"},
         "device-settings-baseline", "snapshots/apps/device-settings/release/doc"),
    ]
    for app, info, name, path in cases:
        info = dict(info, url=URL, arch="aarch64", version="latest")
        assert app_sboms.app_name(app, info) == name
        assert app_sboms.doc_path(app, name, info, "/srv/tqem-fileserver") == pathlib.Path(
            "/srv/tqem-fileserver", path)


def test_url_of_the_bin_folder_finds_the_doc_folder():
    info = {"url": "http://files.example.com/snapshots/apps/backup/main/bin/backup.empkg"}

    assert app_sboms.doc_path("backup", "backup", info, "/srv") == pathlib.Path(
        "/srv/snapshots/apps/backup/main/doc")


def test_sboms_are_copied_from_the_deploy_tree(tmp_path):
    doc = tmp_path / "root" / "snapshots" / "apps" / "backup" / "main" / "doc"
    doc.mkdir(parents=True)
    (doc / "backup.go-sbom.json").write_text("{}")
    defaults = {"url": URL, "branch": "main", "arch": "aarch64", "version": "latest"}
    out = tmp_path / "apps"

    fetched, missing = app_sboms.fetch_apps(defaults, {"backup": {}}, str(out),
                                            str(tmp_path / "root"))

    assert (fetched, missing) == (1, [])
    assert (out / "backup" / "backup.go-sbom.json").read_text() == "{}"


def test_the_deploy_tree_comes_from_the_environment(tmp_path, monkeypatch, capsys):
    doc = tmp_path / "root" / "snapshots" / "apps" / "backup" / "main" / "doc"
    doc.mkdir(parents=True)
    (doc / "backup.go-sbom.json").write_text("{}")
    spec = tmp_path / "spec.yml"
    spec.write_text(f"defaults:\n  url: {URL}\n  branch: main\n  arch: aarch64\n"
                    "  version: latest\napps:\n  backup: {}\n")
    monkeypatch.setenv("TQEM_BASE_DEPLOY_PATH", str(tmp_path / "root"))
    out = tmp_path / "apps"

    app_sboms.main(["--bundle-spec", str(spec), "--output-dir", str(out)])

    assert "SBOMs of 1 apps" in capsys.readouterr().out
    assert (out / "backup" / "backup.go-sbom.json").is_file()


def test_missing_environment_variable_aborts(tmp_path, monkeypatch):
    spec = tmp_path / "spec.yml"
    spec.write_text(f"defaults:\n  url: {URL}\napps:\n  backup: {{}}\n")
    monkeypatch.delenv("TQEM_BASE_DEPLOY_PATH", raising=False)

    with pytest.raises(SystemExit, match="TQEM_BASE_DEPLOY_PATH is not set"):
        app_sboms.main(["--bundle-spec", str(spec), "--output-dir", str(tmp_path / "apps")])


def test_app_without_url_aborts():
    with pytest.raises(app_sboms.AppSbomError, match="no url in the spec for app backup"):
        app_sboms.doc_path("backup", "backup", {"branch": "main"}, "/srv")


def test_url_field_without_value_aborts():
    with pytest.raises(app_sboms.AppSbomError, match="no value for 'branch'"):
        app_sboms.doc_path("backup", "backup", {"url": URL, "arch": "aarch64"}, "/srv")


def test_a_field_of_the_package_name_may_be_missing():
    # emit takes the arch from its command line, the specs of the public bundles leave it open
    info = {"url": "http://files.example.com/apps/{app}/{name}_{version}_{arch}.empkg",
            "version": "latest"}

    assert app_sboms.doc_path("backup", "backup", info, "/srv") == pathlib.Path(
        "/srv/apps/backup/doc")


def test_a_file_url_is_already_the_path_of_the_deploy_tree(monkeypatch):
    # The specs of the locally built apps point at the mount with ${TQEM_BASE_DEPLOY_PATH}
    monkeypatch.setenv("TQEM_BASE_DEPLOY_PATH", "/srv/tqem-fileserver")
    info = {"url": "file://${TQEM_BASE_DEPLOY_PATH}/snapshots/apps/{app}/{branch}/"
                   "{app}_{version}_{arch}.empkg", "branch": "main"}

    assert app_sboms.doc_path("go-demo", "go-demo", info, "/srv/tqem-fileserver") == pathlib.Path(
        "/srv/tqem-fileserver/snapshots/apps/go-demo/main/doc")


def test_environment_variables_are_expanded(monkeypatch):
    monkeypatch.setenv("CI_COMMIT_REF_NAME", "mr-7")
    info = {"url": URL, "arch": "aarch64", "version": "latest", "branch": "$CI_COMMIT_REF_NAME"}

    assert app_sboms.doc_path("backup", "backup", info, "/srv") == pathlib.Path(
        "/srv/snapshots/apps/backup/mr-7/doc")


def test_apps_without_sbom_keep_an_empty_directory(tmp_path):
    doc = tmp_path / "root" / "snapshots" / "apps" / "backup" / "main" / "doc"
    doc.mkdir(parents=True)
    for suffix in ("go-sbom.json", "frontend-sbom.json"):
        (doc / f"backup.{suffix}").write_text("{}")
    defaults = {"url": URL, "branch": "main", "arch": "aarch64", "version": "latest"}
    apps = {"backup": {"version": "latest"}, "presets": {"variant": "tq-embase"},
            "removed-app": None}
    out = tmp_path / "apps"

    fetched, missing = app_sboms.fetch_apps(defaults, apps, str(out), str(tmp_path / "root"))

    assert fetched == 1
    assert missing == ["presets"]
    assert sorted(path.name for path in (out / "backup").iterdir()) == [
        "backup.frontend-sbom.json", "backup.go-sbom.json"]
    assert not list((out / "presets").iterdir())
    assert not (out / "removed-app").exists()


def test_only_the_apps_of_the_bundle_are_read(tmp_path):
    backup = tmp_path / "backup"
    backup.mkdir()
    (backup / "backup.go-sbom.json").write_text(json.dumps({"components": []}))
    (backup / "backup.frontend-sbom.json").write_text(json.dumps({"components": [{"name": "vue"}]}))
    (tmp_path / "other-bundle-app").mkdir()
    (tmp_path / "note.txt").write_text("no app")

    assert app_sboms.read_app_sboms(str(tmp_path), ["backup", "presets"]) == {
        "backup": [{"components": [{"name": "vue"}]}, {"components": []}], "presets": []}

#
# Copyright (c) 2026 TQ-Systems GmbH <license@tq-group.com>, D-82229 Seefeld, Germany. All rights reserved.
# Author: Hans-Christian Melzer and the Energy Manager development team
#
# This software is licensed under the TQ-Systems Product Software License Agreement Version 1.0.3 or any later version.
# You can obtain a copy of the License Agreement in the TQS (TQ-Systems Software Licenses) folder on the following website:
# https://www.tq-group.com/en/support/downloads/tq-software-license-conditions/
# In case of any license issues please contact license@tq-group.com.
#
"""Tests of tqem.bundle with the manifest of a real bundle."""
# pylint: disable=missing-function-docstring
import io
import os
import tarfile

import pytest

from tqem import bundle

MANIFEST = """[update]
compatible=em-aarch64/tq-embase
version=10.0.0
description=EM bundle embase-devel

[hooks]
filename=hook.sh
hooks=install-check;

[image.rootfs]
sha256=f04c41aff9c18cb3e72ede0f77824810e3f56eb4f988e9efedda3f05f2bde074
size=115407096
filename=em-image-embase-release-em-aarch64.tar.xz

[image.u-boot]
filename=bootloaders.txt
hooks=install;
"""


def test_manifest_names_version_and_rootfs_archive(tmp_path):
    (tmp_path / "manifest.raucm").write_text(MANIFEST)

    manifest = bundle.read_manifest(str(tmp_path))

    assert manifest.get("update", "version") == "10.0.0"
    assert manifest.get("update", "compatible") == "em-aarch64/tq-embase"
    assert bundle.rootfs_archive(str(tmp_path), manifest) == str(
        tmp_path / "em-image-embase-release-em-aarch64.tar.xz")


def test_manifest_without_rootfs_image_aborts(tmp_path):
    (tmp_path / "manifest.raucm").write_text("[update]\nversion=10.0.0\n")

    with pytest.raises(ValueError, match="no root file system archive"):
        bundle.rootfs_archive(str(tmp_path), bundle.read_manifest(str(tmp_path)))


def test_missing_manifest_aborts(tmp_path):
    with pytest.raises(FileNotFoundError):
        bundle.read_manifest(str(tmp_path))


def add_file(tar, name, content=b""):
    """Adds a file to a tar archive under construction."""
    info = tarfile.TarInfo(name)
    info.size = len(content)
    tar.addfile(info, io.BytesIO(content))


def write_bundle_dir(tmp_path, *members):
    """Writes a manifest and a root file system archive with the given members."""
    (tmp_path / "manifest.raucm").write_text(
        MANIFEST.replace("em-image-embase-release-em-aarch64.tar.xz", "rootfs.tar"))
    with tarfile.open(tmp_path / "rootfs.tar", "w") as tar:
        for name in members:
            add_file(tar, name, b"x")
    return bundle.read_manifest(str(tmp_path))


def test_apps_of_a_bundle_without_compression(tmp_path):
    manifest = write_bundle_dir(tmp_path, "./opt/apps/backup/manifest.json",
                                "./opt/apps/presets/manifest.json", "./opt/other/file")

    assert bundle.installed_apps(str(tmp_path), manifest, str(tmp_path / "work")) == [
        "backup", "presets"]


def test_apps_of_a_compressed_bundle_come_from_the_apps_image(tmp_path, monkeypatch):
    manifest = write_bundle_dir(tmp_path, "./opt/apps.squashfs")

    def fake_unsquashfs(image, dest_dir, *files):
        assert image.endswith("opt/apps.squashfs") and not files
        os.makedirs(dest_dir)
        os.makedirs(os.path.join(dest_dir, "backup"))
        os.symlink("../../uncompressed-app", os.path.join(dest_dir, "uncompressed-app"))

    monkeypatch.setattr(bundle, "unsquashfs", fake_unsquashfs)

    assert bundle.installed_apps(str(tmp_path), manifest, str(tmp_path / "work")) == [
        "backup", "uncompressed-app"]

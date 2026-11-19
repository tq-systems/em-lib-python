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

#
# Copyright (c) 2026 TQ-Systems GmbH <license@tq-group.com>, D-82229 Seefeld, Germany. All rights reserved.
# Author: Hans-Christian Melzer and the Energy Manager development team
#
# This software is licensed under the TQ-Systems Product Software License Agreement Version 1.0.3 or any later version.
# You can obtain a copy of the License Agreement in the TQS (TQ-Systems Software Licenses) folder on the following website:
# https://www.tq-group.com/en/support/downloads/tq-software-license-conditions/
# In case of any license issues please contact license@tq-group.com.
#
"""Reads RAUC bundles of the Energy Manager: squashfs images, manifest, installed apps.

A spec says what should be installed, the bundle says what is, so the SBOM data comes from here.
"""
import configparser
import os
import subprocess
import tarfile

MANIFEST_FILE = "manifest.raucm"
APPS_DIR = "opt/apps/"
APPS_IMAGE = "opt/apps.squashfs"


def unsquashfs(image, dest_dir, *files):
    """Extracts a squashfs image, e.g. a RAUC bundle, to dest_dir.

    Without files the whole image is extracted, otherwise only the named ones.
    """
    subprocess.run(["unsquashfs", "-q", "-no-progress", "-d", dest_dir, image, *files], check=True)


def read_manifest(bundle_dir):
    """Returns the manifest of an extracted bundle, e.g. manifest.get("update", "version")."""
    manifest = configparser.ConfigParser(interpolation=None)
    with open(os.path.join(bundle_dir, MANIFEST_FILE), encoding="utf-8") as manifest_file:
        manifest.read_file(manifest_file)
    return manifest


def rootfs_archive(bundle_dir, manifest):
    """Returns the path of the root file system archive that the manifest names.

    A bundle can hold further archives, the rootfs slot names the one to install.
    """
    filename = manifest.get("image.rootfs", "filename", fallback=None)
    if not filename:
        raise ValueError(f"{MANIFEST_FILE} in {bundle_dir} names no root file system archive")
    return os.path.join(bundle_dir, filename)


def installed_apps(bundle_dir, manifest, work_dir):
    """Returns the names of the apps a bundle installs, sorted.

    Without compression the apps lie below opt/apps of the root file system, with compression in
    opt/apps.squashfs next to it. An app that emit installs uncompressed lies below opt/<app> and
    the apps image links to it, so its name shows up in the image either way.
    """
    apps = set()
    apps_image = None
    with tarfile.open(rootfs_archive(bundle_dir, manifest)) as tar:
        for member in tar:
            name = os.path.normpath(member.name)
            if name == APPS_IMAGE:
                tar.extract(member, work_dir, filter="data")
                apps_image = os.path.join(work_dir, APPS_IMAGE)
            elif name.startswith(APPS_DIR):
                apps.add(name[len(APPS_DIR):].split("/")[0])
    if apps_image:
        apps_dir = os.path.join(work_dir, "apps")
        unsquashfs(apps_image, apps_dir)
        apps.update(os.listdir(apps_dir))
    return sorted(apps)


def extract_bundle(raucb_path, work_dir):
    """Extracts a RAUC bundle below work_dir and returns its manifest and its apps."""
    bundle_dir = os.path.join(work_dir, "bundle")
    unsquashfs(raucb_path, bundle_dir)
    manifest = read_manifest(bundle_dir)
    return manifest, installed_apps(bundle_dir, manifest, work_dir)

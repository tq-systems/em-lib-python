#!/bin/bash
#
# Copyright (c) 2026 TQ-Systems GmbH <license@tq-group.com>, D-82229 Seefeld, Germany. All rights reserved.
# Author: Hans-Christian Melzer and the Energy Manager development team
#
# This software is licensed under the TQ-Systems Product Software License Agreement Version 1.0.3 or any later version.
# You can obtain a copy of the License Agreement in the TQS (TQ-Systems Software Licenses) folder on the following website:
# https://www.tq-group.com/en/support/downloads/tq-software-license-conditions/
# In case of any license issues please contact license@tq-group.com.
#

# Sets the project version, called by em-release-commit with the release version.

set -e

VERSION="${1#v}"
PYPROJECT_FILE="pyproject.toml"

[ -n "$VERSION" ] || { echo >&2 "Usage: $(basename "$0") <version>"; exit 1; }

set_project_version() {
	sed -i "s/^\(version = \"\)[^\"]*\"/\1${1}\"/" "$PYPROJECT_FILE"
}

set_project_version "$VERSION"
git add "$PYPROJECT_FILE"

# Python library

## Description
This Python library holds the Python code of the TQ Energy Manager build tools.
The public toolchain installs it and calls its executables from the make targets.
The code can be tested without the toolchain.

## Structure of the project
- `tqem`: the library modules, see `tqem/README.md`
- `tests`: the unit tests, see `tests/README.md`

## Executables
- `tqem-bundle-sbom`: merges the app SBOMs of a RAUC bundle and the core image SBOM into one
  CycloneDX file per bundle
- `tqem-go-sbom-licenses`: writes the licenses of the go-licenses manifest into the Go SBOM of an app

Each executable shows its options with `--help`.

## Development
Ubuntu needs the package `python3-venv`. The make targets create a virtual environment in `.venv`
and install the library with its test tools in editable mode:

    make test
    make lint

## Installation
The toolchain installs a released version from GitHub:

    pip install git+https://github.com/tq-systems/em-lib-python@v1.0.0

## Release
Raise the version in `pyproject.toml` and tag the commit with the same version, e.g. `v1.0.0`.
The tag pipeline fails if both differ, because the SBOMs carry the version from `pyproject.toml`.

## License information
This project is licensed under the TQSPSLA-1.0.3 license, see LICENSE file for further details.

    SPDX-License-Identifier: LicenseRef-TQSPSLA-1.0.3

All files in this project are classified as product-specific software and bound
to the use with the TQ-Systems GmbH product: EM400

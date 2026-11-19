# tqem

| Module | Content |
|--------|---------|
| `app_sboms` | Collects the app SBOMs of a bundle from the deploy tree, executable `tqem-fetch-app-sboms` |
| `bundle` | Reads RAUC bundles: squashfs extraction, manifest, installed apps |
| `bundle_sbom` | Merges the app SBOMs of a bundle and the core image SBOM, executable `tqem-bundle-sbom` |
| `go_sbom_licenses` | Takes the Go SBOM licenses from the go-licenses manifest, executable `tqem-go-sbom-licenses` |

## App SBOM collection
`app_sboms` keeps no deploy path of its own. It takes the package URL of every app from the bundle
specs, reads its path below `TQEM_BASE_DEPLOY_PATH` and copies the SBOMs out of the `doc` folder
of that deploy folder. The runners and the developer machines carry that variable and mount the
tree, so both work the same way. Environment variables of a spec URL are expanded. An app without
SBOM keeps an empty directory and shows up in the bundle SBOM as `emos.apps_without_sbom`:

    tqem-fetch-app-sboms --bundle-spec bundle.yml --output-dir /tmp/app-sboms

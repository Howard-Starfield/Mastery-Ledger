# Release process

Mastery Ledger has two release surfaces: the Python application and the `mastery-ledger/` Codex skill. The application is currently version `0.1.3`; compatibility with the skill is communicated through the versioned `doctor-v2` contract. The contract exposes application readiness only; source and course tooling belongs to the skill.

## Automated gates

Every push and pull request runs the Python and skill contract suite on Python 3.11 and 3.12 across Windows and Ubuntu. It also installs the locked frontend dependencies, runs Vitest, rebuilds the Vite bundle, and rejects source changes that do not include the matching bundled assets.

A tag matching `v*` starts the release workflow. The workflow requires the tag to equal the version in `pyproject.toml`, reruns tests, builds the wheel and source distribution, archives the matching Codex skill, builds the portable Windows application, loads its native pywebview/.NET runtime, compiles and silently installs the Inno Setup installer, creates `SHA256SUMS.txt`, records GitHub artifact attestations, uploads immutable workflow artifacts, and creates the GitHub release. The in-app updater discovers the latest stable release through GitHub's release API and requires the exact `MasteryLedger-windows-x64-v<version>.zip` asset plus its GitHub SHA-256 digest. The installer EXE is the primary human download; the ZIP remains the updater and portable payload.

## Maintainer checklist

1. Update the application version in `pyproject.toml`, `src/mastery_ledger/__init__.py`, and the frontend package metadata together. Keep any fixed download name in the README aligned with the release tag.
2. Regenerate `requirements/core.lock`, `requirements/desktop.lock`, `requirements/media.lock`, and `requirements/transcription.lock` when Python dependency ranges change. The desktop lock includes the `desktop` and `desktop-build` extras; the transcription lock includes both the `media` and `transcription` extras.
3. Run the commands in the README's local development and test section from a clean checkout. Local distribution builds must start without a stale generated `build/` directory so retired frontend hashes cannot leak into the wheel.
4. Commit and push the release candidate; wait for CI to pass.
5. Create and push the matching annotated version tag, such as `v0.1.3`.
6. Verify the release's checksums and GitHub artifact attestation before recommending it.

## Signing boundary

The repository can produce checksummed, provenance-attested Python artifacts and an unsigned Windows installer without private credentials. It cannot produce a trusted OS installer signature by itself. Windows Authenticode and macOS notarization require maintainer-controlled signing identities and protected CI secrets. Until those credentials are configured, releases remain developer previews and the skill must not describe them as signed learner-ready installers.

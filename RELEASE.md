# Release process

Mastery Ledger has two release surfaces: the Python application and the `mastery-ledger/` Codex skill. The application is currently version `0.1.1`; compatibility with the skill is communicated through the versioned `doctor-v2` contract. The contract exposes application readiness only; source and course tooling belongs to the skill.

## Automated gates

Every push and pull request runs the Python and skill contract suite on Python 3.11 and 3.12 across Windows and Ubuntu. It also installs the locked frontend dependencies, runs Vitest, rebuilds the Vite bundle, and rejects source changes that do not include the matching bundled assets.

A tag matching `v*` starts the release workflow. The workflow requires the tag to equal the version in `pyproject.toml`, reruns tests, builds the wheel and source distribution, archives the matching Codex skill, builds and smoke-tests the portable Windows application, creates `SHA256SUMS.txt`, records GitHub artifact attestations, uploads immutable workflow artifacts, and creates the GitHub release.

## Maintainer checklist

1. Update the application version in `pyproject.toml`, `src/mastery_ledger/__init__.py`, and the frontend package metadata together. Keep any fixed download name in the README aligned with the release tag.
2. Regenerate `requirements/core.lock`, `requirements/desktop.lock`, `requirements/media.lock`, and `requirements/transcription.lock` when Python dependency ranges change. The desktop lock includes the `desktop` and `desktop-build` extras; the transcription lock includes both the `media` and `transcription` extras.
3. Run the commands in the README's automated-check section from a clean checkout. Local distribution builds must start without a stale generated `build/` directory so retired frontend hashes cannot leak into the wheel.
4. Commit and push the release candidate; wait for CI to pass.
5. Create and push the matching annotated version tag, such as `v0.1.1`.
6. Verify the release's checksums and GitHub artifact attestation before recommending it.

## Signing boundary

The repository can produce checksummed, provenance-attested Python artifacts without private credentials. It cannot produce a trusted OS installer signature by itself. Windows Authenticode and macOS notarization require maintainer-controlled signing identities and protected CI secrets. Until those credentials and installer jobs are configured, releases remain developer previews and the skill must not describe them as signed learner-ready installers.

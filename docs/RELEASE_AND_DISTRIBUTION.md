# Release and Distribution

This repo ships three public surfaces: PyPI, the GitHub Action, and the MCP
Registry entry. Releases are tag-driven and tokenless where the platform allows
it.

## PyPI trusted publishing

The release workflow is `.github/workflows/release.yml`. It publishes only on a
`vX.Y.Z` tag and requires these versions to agree before upload:

- `pyproject.toml` project version
- `action.yml` install pin
- the pushed tag name

One-time PyPI owner setup, done in the browser:

1. Open `pypi.org/project/signalbrain/`.
2. Manage project -> Publishing -> Add a new pending publisher.
3. Owner: `whitestone1121-web`.
4. Repository: `signalbrain`.
5. Workflow name: `release.yml`.
6. Environment name: `pypi`.

After that, pushing `vX.Y.Z` is enough; no PyPI token is stored in GitHub.

## GitHub Action Marketplace

The composite Action is `action.yml`. To publish it in Marketplace, use the
GitHub release UI for the new tag and choose "Publish this Action to the GitHub
Marketplace". The Action pin must match the package version released to PyPI.

Recommended short description:

> Score merged SignalBrain receipts and enforce calibrated per-class trust.

Recommended categories: `Code quality`, `Continuous integration`, `Utilities`.

## MCP Registry

After the PyPI version is live, run the manual workflow:

```bash
gh workflow run publish-mcp.yml
```

The workflow checks that `server.json` matches `pyproject.toml`, verifies the
PyPI release exists, authenticates with GitHub OIDC, and publishes the MCP
server descriptor.

## Fresh-install smoke

Run this after each PyPI release:

```bash
python3 -m venv /tmp/signalbrain-smoke
/tmp/signalbrain-smoke/bin/pip install --upgrade pip
/tmp/signalbrain-smoke/bin/pip install signalbrain==0.1.3
/tmp/signalbrain-smoke/bin/sb --help
/tmp/signalbrain-smoke/bin/sb gate --help
```

For MCP smoke after the MCP extra is live:

```bash
uvx --from "signalbrain[mcp]==0.1.3" sb-mcp --help
```

# Release Process

**Project:** AbstrHActor (Home Assistant custom_component)
**Distribution:** HACS
**Version Control:** Git with Conventional Commits
**Version Format:** Semantic Versioning (MAJOR.MINOR.PATCH)

---

## Overview

This document defines the complete lifecycle for releasing AbstrHActor versions to HACS and GitHub. The process balances automation with human review: tests and validation are automated; version bumping and changelog review are manual.

**Key principle:** Every release is tagged in git, published on GitHub Releases, and automatically made available to HACS end-users within ~24 hours (HACS sync interval).

---

## Versioning Scheme

### Semantic Versioning (SemVer)

AbstrHActor follows **Semantic Versioning 2.0.0** (https://semver.org/):

```
MAJOR.MINOR.PATCH

Example: 1.2.3
         ↑    ↑  ↑
    Breaking  New  Bugfix
    change   feature
```

**Format in `custom_components/abstractor/manifest.json`:**
```json
{
  "version": "1.2.3"
}
```

**HACS version discovery:**
- HACS reads the `version` field from `manifest.json` and compares it to available GitHub Releases
- Tag names in GitHub should match the version (e.g., `v1.2.3` or `1.2.3`)
- HACS does NOT store a version field in `hacs.json` — HACS reads versions from GitHub Releases API

### Version Bump Rules

| Type of Change | Bump | Example | User Impact |
|---|---|---|---|
| Breaking change (removed config option, incompatible config schema, incompatible entity changes) | MAJOR | 1.0.0 → 2.0.0 | Requires manual migration |
| New feature (new sensor type, new config option, new service) | MINOR | 1.2.0 → 1.3.0 | Backward compatible; users get new capability |
| Bugfix (incorrect calculation, UI fix, config flow fix) | PATCH | 1.2.0 → 1.2.1 | Backward compatible; recommended for all users |
| Documentation or non-functional (docs, tests, CI) | PATCH or none | See note below | No release needed if tests/docs only |

**Note on documentation-only commits:** If a release contains only `docs:` or `test:` commits with no feature/fix changes, release management may elect not to bump the patch version. This is optional; conservative teams may increment PATCH anyway.

---

## Deciding on a Version Bump

### Process

1. **List commits since last release tag:**
   ```bash
   git log <last-tag>..HEAD --oneline --format='%h %s'
   ```
   Example output:
   ```
   e27fc30 feat: add Abstractor sidebar panel and E2E test suite
   d86df6b test(e2e): fix Playwright locators and document Docker reset
   b302750 fix(config_flow): remove read-only property setter in OptionsFlowHandler
   ```

2. **Analyze commit types:**
   - Count `feat:` commits → informs MINOR bump
   - Count `fix:` commits → informs PATCH bump
   - Check for breaking changes in commit body (look for "BREAKING CHANGE:" in message)

3. **Determine bump:**
   - If ANY commit has "BREAKING CHANGE:" → **bump MAJOR**
   - Else if ANY `feat:` commit exists → **bump MINOR**
   - Else if ANY `fix:` commit exists → **bump PATCH**
   - Else (docs/test/chore only) → **optional PATCH bump** (see note above)

4. **Document decision in CHANGELOG.md** (see below)

**Example:**
- Last release: `v1.0.0`
- Commits since: 3 `feat:`, 2 `fix:`, 1 `test:`
- Decision: bump MINOR → `v1.1.0`

---

## CHANGELOG.md Format

### Keep a Changelog

AbstrHActor uses the **Keep a Changelog** format (https://keepachangelog.com/):

**File location:** `CHANGELOG.md` (repository root)

**Format:**

```markdown
# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [1.2.3] — 2025-02-15

### Added
- Sidebar panel for Abstractor config and diagnostics
- E2E test suite with Playwright and Docker integration

### Fixed
- Config flow options handler no longer allows read-only property setter
- Playwright locators updated for latest HA UI changes

### Changed
- (None in this release)

### Removed
- (None in this release)

## [1.0.0] — 2025-01-20

### Added
- Initial public release
- Config flow with unique IDs
- Power, energy, and water sensor aggregation
- Spike filter and monotonic guards
- Export/import snapshot services
- Diagnostics integration
```

### Sections (use as needed)

- **Added** — new features, config options, new entity types
- **Fixed** — bugfixes, performance improvements
- **Changed** — behavior changes, re-architecture (backward compatible)
- **Removed** — deprecated features, removed config options
- **Security** — vulnerability fixes (if any)

### Guidelines

1. **Date format:** ISO 8601 (`YYYY-MM-DD`)
2. **Section headers:** Always present in the template; omit a section if empty for that version
3. **Entries:** Bullet points; group by semantic meaning (not by commit)
4. **Traceability:** Optional: include commit hashes or REQ IDs if the project uses requirements tracking (e.g., `feat: sidebar panel ([e27fc30](https://github.com/...))`)
5. **User-facing language:** Write for HA users, not developers
   - Good: "Sidebar panel now shows device diagnostics"
   - Avoid: "Refactored XYZ to use new pattern"

### Maintenance

- **Manual:** CHANGELOG is maintained by hand, not auto-generated from commits
  - Rationale: Allows grouping, emphasis, and user-facing language
  - Rationale: Catches missing commits or commits that should not be in the changelog
- **Unreleased section:** Optionally keep an `## [Unreleased]` section at the top to track in-progress changes, but this is not required

---

## Pre-Release Checklist

Before tagging and releasing, verify:

| Item | Command | Expected |
|---|---|---|
| Tests pass | `pytest tests/ -v --cov=custom_components/abstractor --cov-report=term-missing` | 100% pass rate, acceptable coverage |
| Hassfest validation passes | `python3 -m script.hassfest --integration-path custom_components/abstractor` (or the `hassfest` job in `.github/workflows/validate.yaml`) | No errors — checks `manifest.json` schema, brand icons |
| HACS validation passes | `hacs/action` in the `hacs` job of `.github/workflows/validate.yaml` | Green check — checks `hacs.json` schema, README, repository description/topics |
| manifest.json version bumped | Check `custom_components/abstractor/manifest.json` | Matches intended release version (e.g., "1.2.3") |
| CHANGELOG.md updated | Check `CHANGELOG.md` | Includes new version section with date and all changes |
| No uncommitted changes | `git status` | Clean working tree |
| Commits reviewed | `git log origin/main..HEAD` | All commits follow Conventional Commits format |

---

## Release Workflow: Step-by-Step

### Step 1: Prepare Release Branch (Optional)

Most releases do NOT require a separate release branch; follow the standard PR workflow:

1. **On your development branch** (e.g., `feat/my-feature`):
   - Code + tests are complete
   - Commits follow Conventional Commits

2. **Create a Pull Request** to `main`
   - GitHub Actions runs validation (HACS + hassfest)
   - Code review and approval

3. **Merge to `main`**
   - All commits now on `main`

### Step 2: Create Release Commit

On a local checkout of `main` (up to date):

1. **Analyze commits since last tag:**
   ```bash
   git log v<LAST-VERSION>..HEAD --oneline --format='%h %s'
   ```

2. **Decide on version bump** (see "Deciding on a Version Bump" section)
   - Example decision: last version is `v1.0.0`, next version is `v1.1.0`

3. **Update CHANGELOG.md:**
   - Add new version section with date
   - List all changes (Added, Fixed, Changed, Removed)
   - Commit message: `chore: release v1.1.0`
   ```bash
   # Edit CHANGELOG.md (add new version section at top, below Unreleased if present)
   git add CHANGELOG.md
   git commit -m "chore: release v1.1.0"
   ```

4. **Update manifest.json:**
   ```bash
   # Edit custom_components/abstractor/manifest.json
   # Change "version": "1.0.0" → "version": "1.1.0"
   git add custom_components/abstractor/manifest.json
   git commit -m "chore: bump version to 1.1.0"
   ```

   **Or combine both commits if preferred:**
   ```bash
   git add CHANGELOG.md custom_components/abstractor/manifest.json
   git commit -m "chore: release v1.1.0"
   ```

5. **Push to origin:**
   ```bash
   git push origin main
   ```

### Step 3: Create Git Tag

After release commits are pushed to `main`:

```bash
# Fetch latest
git fetch origin main

# Create annotated tag (preferred for releases)
git tag -a v1.1.0 -m "Release v1.1.0"

# Push tag to GitHub
git push origin v1.1.0
```

**Tag naming convention:** `v<MAJOR>.<MINOR>.<PATCH>` (with leading `v`)
- Example: `v1.0.0`, `v1.1.0`, `v2.0.0`
- Note: Both `v1.1.0` and `1.1.0` formats are valid in HACS; this project uses the `v` prefix for consistency

### Step 4: Automatic Release Automation (Future)

Once `.github/workflows/release.yaml` is implemented (see "Future Automation" section):
- Pushing a tag automatically triggers the release workflow
- Workflow verifies tests, manifest.json version, CHANGELOG.md entry
- Workflow creates GitHub Release with CHANGELOG content
- **No manual work needed after the tag push**

For now (while automation is not yet implemented):

### Step 4 (Current): Manual GitHub Release Creation

1. **On GitHub web UI:**
   - Navigate to **Releases** tab
   - Click **"Draft a new release"**

2. **Fill in release details:**
   - **Tag:** Select the tag you just pushed (e.g., `v1.1.0`)
   - **Release title:** `v1.1.0` or `Release v1.1.0`
   - **Description:** Copy the relevant section from CHANGELOG.md
     - Format: Use markdown headings, bullet points
     - Example:
       ```markdown
       ## Added
       - Sidebar panel for Abstractor config and diagnostics
       - E2E test suite with Playwright and Docker integration

       ## Fixed
       - Config flow options handler no longer allows read-only property setter
       ```

3. **Publish release:**
   - Click **"Publish release"**
   - GitHub will create a release asset for the tag

4. **Verify HACS pickup:**
   - Within 24 hours, HACS will fetch the new release from GitHub
   - Users will see the new version available for update

---

## Future Automation: Release Workflow

Once `.github/workflows/release.yaml` is implemented, the following automation can be added:

**Workflow trigger:** `push` with tag pattern `v*`

**Workflow steps:**

1. Checkout code at the tag commit
2. Run tests: `pytest tests/ -v`
3. Run HACS validation: `hacs action`
4. Run hassfest: `home-assistant/actions/hassfest`
5. Extract version from tag (e.g., `v1.1.0` → `1.1.0`)
6. Verify `manifest.json` version matches
7. Verify `CHANGELOG.md` contains entry for this version
8. Extract CHANGELOG content for this version
9. Create GitHub Release with CHANGELOG content as description
10. Optional: Attach a `.zip` artifact of `custom_components/abstractor/` for manual deployment

**Example workflow structure:**

```yaml
name: Release

on:
  push:
    tags:
      - 'v*'

jobs:
  release:
    name: Create Release
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Install dependencies
        run: pip install -r requirements_test.txt
      - name: Run tests
        run: pytest tests/ -v
      - name: HACS validation
        uses: hacs/action@main
        with:
          category: integration
      - name: Hassfest validation
        uses: home-assistant/actions/hassfest@master
      - name: Create Release
        uses: actions/create-release@v1
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        with:
          tag_name: ${{ github.ref }}
          release_name: Release ${{ github.ref }}
          body: ${{ env.RELEASE_NOTES }}
          draft: false
          prerelease: false
```

---

## FAQ

### Q: What if I need to fix a bug in a released version?

**A:** Create a hotfix branch from the release tag:

```bash
git checkout -b hotfix/critical-bug v1.0.0
# Make fixes
git commit -m "fix: critical bug description"
git push origin hotfix/critical-bug
# Create PR to main, merge normally
# Then follow release process for v1.0.1
```

### Q: Can I skip PATCH bumps if there are only bugfixes?

**A:** No. Bugfixes increment PATCH (e.g., `1.0.0` → `1.0.1`). This signals to users that updates are available and important.

### Q: What if I want to release a pre-release (alpha/beta)?

**A:** Append a pre-release suffix to the version per SemVer:
- `1.1.0-alpha.1` (first alpha)
- `1.1.0-beta.1` (beta)
- `1.1.0-rc.1` (release candidate)

Update both manifest.json version and the git tag:

**manifest.json:**
```json
"version": "1.1.0-alpha.1"
```

**Git tag:**
```bash
git tag v1.1.0-alpha.1
git push origin v1.1.0-alpha.1
```

**HACS behavior:**
- HACS recognizes pre-release tags via the GitHub Releases API
- Pre-releases are NOT automatically offered to end-users
- Users can opt-in to pre-releases in HACS settings or by explicitly updating to the pre-release version
- This allows testing new features before a stable release

### Q: What if manifest.json version doesn't match the tag?

**A:** This breaks the release automation and is a blocker. The release workflow will check this and fail if mismatched. To fix:

```bash
# If tag is v1.1.0 but manifest says "1.0.0":
git checkout v1.1.0
# Fix manifest.json version to "1.1.0"
git commit --amend custom_components/abstractor/manifest.json
git tag -d v1.1.0
git tag v1.1.0
git push origin v1.1.0 -f  # ⚠️ Force push only if tag hasn't propagated widely
```

### Q: Who can trigger a release?

**A:** Maintainers with push access to the repository and GitHub release creation permissions. Currently: `@Popoboxxo` (codeowner).

### Q: How are versions communicated to users?

**A:** 
- **GitHub Releases page:** Latest releases visible at https://github.com/Popoboxxo/AbstrHActor/releases
- **HACS UI:** Users see available versions in HACS settings under "Installed integrations"
- **Changelog:** Linked in GitHub release body; users refer to it for upgrade notes

---

## HACS Configuration Reference

**hacs.json fields:**
```json
{
  "name": "Integration Name",
  "homeassistant": "2025.1.0",
  "render_readme": true,
  "hacs": "1.0.0"
}
```

- `name` (required): Display name in HACS UI
- `homeassistant` (required): Minimum supported Home Assistant version
- `render_readme` (optional): If true, HACS renders your README.md as the integration description
- `hacs` (optional): Minimum supported HACS version
- `zip_release` (deprecated): Older HACS versions used this to control .zip creation; no longer needed

**DO NOT include** in hacs.json:
- `version` — HACS reads this from GitHub Releases and manifest.json instead
- `domain` — only in manifest.json
- `iot_class` — only in manifest.json
- Any manifest.json fields

---

## Tools & References

- **Git:** https://git-scm.com/
- **Semantic Versioning:** https://semver.org/
- **Conventional Commits:** https://www.conventionalcommits.org/
- **Keep a Changelog:** https://keepachangelog.com/
- **HACS Documentation:** https://hacs.xyz/docs/publish/
- **HACS Action:** https://github.com/hacs/action
- **Home Assistant:** https://www.home-assistant.io/

---

## History

| Version | Date | Notes |
|---|---|---|
| 1.0 | 2026-08-08 | Initial release process definition (no automation yet) |

---

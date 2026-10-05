# Fixture Test Hygiene Specification

## Purpose

Make portal validation tests deterministic, offline, and honest: every assertion runs against committed sanitized fixtures, and genuinely optional network tests skip explicitly instead of passing vacuously.

## Requirements

### Requirement: Replace vacuous conditional assertions with committed fixtures

Portal validation tests MUST assert URL-validation semantics against committed, sanitized fixtures. A test body MUST NOT report PASS when its conditional assertions are skipped because a temporary host file is absent. Genuinely optional network probes MUST skip via `pytest.skip` with a clear message.

#### Scenario: Fixture-backed validation runs offline

- GIVEN committed sanitized portal fixtures for the supported portals under test
- WHEN the portal validation test suite runs without network access
- THEN every portal validation assertion executes against a committed fixture
- AND no test depends on `/tmp/*-live.html`

#### Scenario: Optional live probe skips explicitly

- GIVEN a genuinely optional network-dependent live probe
- WHEN its prerequisite data is unavailable
- THEN the test is reported as skipped with a clear reason
- AND it is not reported as passed

### Requirement: Isolate test configuration from host state

Tests that resolve a user profile MUST use an isolated temporary configuration fixture and MUST NOT depend on the developer's working-directory or untracked `user_profile.yml`. A documented happy path MUST have the same result regardless of the host profile.

#### Scenario: Test result is independent of host profile

- GIVEN the developer's working directory contains a profile with any municipality
- WHEN the portal validation tests run
- THEN the outcome is determined solely by the test's temporary configuration fixture

#### Scenario: Config path is explicitly provided

- GIVEN a validation test needs a profile
- WHEN it resolves configuration
- THEN it points `HOME_OPS_CONFIG` or equivalent to a `tmp_path`-scoped fixture profile
- AND the resolved path is independent of the current working directory

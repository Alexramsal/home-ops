# Source Verification Specification

## Purpose

Define a trustworthy `sources validate` contract that verifies parsed listing evidence against the configured search municipality without evading portal protections.

## Requirements

### Requirement: Verify parsed listing locations before marking a source verified

The system MUST compare normalized, unambiguous municipality evidence from parsed sample listings against configured `search.municipality`. A source SHALL be `verified` only when `resolved = matched + mismatched > 0` and `matched / resolved > 0.5`. Unresolved items are excluded from the denominator and never count as matches. No resolved locations, province/district-only evidence, an exact tie, or a share below the threshold MUST produce an explicit non-verified result: `ambiguous` for absent/insufficient evidence or ties, `mismatch` for below-threshold resolved evidence. Diagnostics MUST report parsed, matched, mismatched, unresolved, and resolved counts plus the matching share (undefined when resolved is zero). URL text alone MUST NOT establish verification, and a province or district name alone MUST NOT be treated as municipality evidence.

#### Scenario: Matching sample listings are accepted

- GIVEN a supported source URL and a profile with `search.municipality` set to `Chiclana de la Frontera`
- AND the parser returns non-empty listings whose resolved locations match that municipality
- WHEN `sources validate` runs
- THEN validation succeeds and reports the portal and parsed item count

#### Scenario: Cross-municipality sample listings are rejected

- GIVEN a supported source URL and a configured municipality
- AND parsed listings clearly identify a different municipality
- WHEN `sources validate` runs
- THEN validation fails
- AND the diagnostic identifies the configured municipality and observed mismatch

#### Scenario: Mixed sample evidence uses an explicit consensus rule

- GIVEN parsed listings where some locations match and others do not
- WHEN `sources validate` runs
- THEN the result follows the defined minimum matching-share rule
- AND the diagnostic reports the observed location distribution and matching share

### Requirement: Represent insufficient source evidence as ambiguous

The system MUST NOT mark a source verified when parsed evidence is absent or insufficient under the resolved-item consensus rule. An opaque or ID-only URL neither proves nor prevents verification: parsed content satisfying `matched / resolved > 0.5` can verify it. Without that evidence, validation MUST return an explicit non-verified result explaining what operator evidence or follow-up validation is required.

#### Scenario: ID-only URL lacks textual location evidence

- GIVEN a supported URL containing only an opaque listing or search ID
- AND parsed listings do not expose a municipality
- WHEN validation runs
- THEN it returns an ambiguous result rather than rejecting or accepting solely from the URL
- AND no source is persisted as verified

#### Scenario: Missing location fields are reported

- GIVEN a parser returns listings without usable `location`, `address`, or equivalent municipality data
- WHEN validation runs
- THEN the result states that location evidence is insufficient
- AND the parsed item count remains visible

### Requirement: Preserve safe validation boundaries

The system MUST continue rejecting unsupported domains, empty responses, parse failures, and anti-bot challenges with actionable diagnostics. Validation MUST use only the permitted ordinary fetch/parser path and MUST NOT bypass access controls.

#### Scenario: Anti-bot challenge prevents verification

- GIVEN a supported URL whose response is an anti-bot challenge
- WHEN validation runs
- THEN it fails with the detected challenge reason
- AND it does not classify the source as verified

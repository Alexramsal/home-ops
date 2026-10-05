# Configuration and Documentation Alignment Specification

## Purpose

Harmonize system configuration, profile setup, CLI defaults, installation instructions, and scoring documentation so that commands, templates, and guides accurately reflect the runtime implementation.

## Requirements

### Requirement: Harmonize configuration keys and profile tooling

All user-facing documentation (`README.md`, `AGENTS.md`) and CLI instructions MUST use exact runtime key paths under `scoring.thresholds.*` for scoring parameters, such as `scoring.thresholds.price_median`. The template `config/user_profile.template.yml` MUST contain valid nested structure without dead keys, and `profile set` MUST validate nested key paths. Profile setup commands MUST allow expressing or preserving `search` parameters.

#### Scenario: Documented `profile set` command executes successfully

- GIVEN a profile initialized from the template
- WHEN an operator runs `uv run homeops profile set scoring.thresholds.price_median 2100`
- THEN the key updates successfully without a key error

#### Scenario: Obsolete flat scoring keys are rejected

- GIVEN an operator attempts to run `profile set scoring.price_median 2100`
- WHEN the command runs
- THEN it fails with an explicit error directing to `scoring.thresholds.price_median`

#### Scenario: Setup wizard captures search configuration

- GIVEN `homeops setup` runs
- WHEN the operator provides search municipality, max price, or min area
- THEN the resulting configuration persists a `search` block matching the user's intent

### Requirement: Align template portal sources with municipality

The template `config/user_profile.template.yml` MUST configure source URLs that match its own declared `search.municipality`. Sources that target an entire province or another municipality MUST NOT be presented as valid for the template's specific city.

#### Scenario: Template validation is self-consistent

- GIVEN `config/user_profile.template.yml` declares `search.municipality: Chiclana de la Frontera`
- WHEN `sources validate` evaluates the template's initial URLs against that municipality
- THEN none of the initial URLs fail due to a municipality mismatch against the template's own setting

### Requirement: Align CLI defaults, installation extras, and web/TUI guidance

The web server default port MUST be 8000 across `homeops web` CLI defaults, help strings, `README.md`, and `AGENTS.md`. Installation instructions MUST document the optional extras (`[web]`, `[tui]`) required to execute dashboard and terminal interface commands.

#### Scenario: Default web command matches documentation

- GIVEN a user runs `uv run homeops web` without specifying `--port`
- WHEN the server starts
- THEN it listens on port 8000 as documented

#### Scenario: Installation docs include required extras for web and TUI

- GIVEN a user follows the installation section in `README.md`
- WHEN they execute `homeops web` or `homeops tui`
- THEN all required dependencies are present without missing module errors

### Requirement: Accurately document scoring signals and LLM behavior

Scoring documentation in `README.md` and `AGENTS.md` MUST accurately reflect runtime scoring behavior:
- Energy certificate scoring MUST be described as binary presence (0.0 or 1.0), not a letter grade.
- Price comparison MUST be described as a comparison against zone median price per m2, not a range.
- LLM risk penalties MUST be documented as deterministic subtractions from the final score.
- Non-Spanish affordability scoring MUST be documented as deactivated, with its weight redistributed across active rules.

#### Scenario: Energy certificate score matches documentation

- GIVEN a listing with an energy certificate of any letter grade
- WHEN it is evaluated by the deterministic scorer
- THEN it receives the full binary presence score (1.0 weight) as documented

#### Scenario: LLM risk flag affects deterministic score

- GIVEN an LLM analysis identifies known risk flags for a listing
- WHEN the deterministic score is computed
- THEN the risk flag penalties subtract from the final score as documented

#### Scenario: Non-ES listing deactivates affordability rule

- GIVEN a listing located outside Spain
- WHEN scoring is executed
- THEN the affordability rule returns 0.0 with 0.0 weight and its weight is redistributed among remaining active rules as documented

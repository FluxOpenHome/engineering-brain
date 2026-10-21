# ADR-0004: Reference standards, do not redistribute them

Status: accepted, 2026-10-21

## Context
ISO, IEEE, ASHRAE and other standards bodies now prohibit storing or processing their text in AI
tools in their licence terms; US fair-use decisions cover only non-commercial republication of
standards incorporated into law.

## Decision
Documents of type `standard` are ingested under a policy that, by default, stores clause
identifiers, titles and the organisation's own derived parameters, and processes licensed text
only ephemerally under the user's licence during a check. A per-licence override may enable full
text indexing where the organisation's licence permits it. Spec templates reference standards by
clause ID only.

## Consequences
- Compliance checks against a standard run on the user's licensed copy at check time.
- Requirement sets store the organisation's own requirement sentences, not the standard's text.

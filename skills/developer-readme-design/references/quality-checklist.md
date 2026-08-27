# README Quality Checklist

Run this checklist before finalizing a README.

## First-screen comprehension

- [ ] Can a developer understand what the project is within 5 seconds?
- [ ] Is the main audience obvious?
- [ ] Is the primary value proposition concrete?
- [ ] Is there a visible Quick Start / install path?

## Information architecture

- [ ] Does each section add new information?
- [ ] Are repeated component descriptions removed?
- [ ] Are advanced details moved below the core onboarding path?
- [ ] Is the section order natural: understand → evaluate → install → use → dive deeper?

## Visual system

- [ ] Are emoji absent as the main icon system?
- [ ] Are badges limited and consistent?
- [ ] Are SVGs used only when they improve comprehension or identity?
- [ ] Are component icons visually consistent?
- [ ] Does the page remain readable without images?

## GitHub compatibility

- [ ] Is Markdown doing most of the work?
- [ ] Is HTML limited to safe structural elements?
- [ ] Is there no reliance on JavaScript or custom CSS?
- [ ] Are repository image paths valid?
- [ ] Do diagrams and logos work in dark and light themes?

## Technical correctness

- [ ] Are install commands copied from real project configuration or docs?
- [ ] Are package names correct?
- [ ] Are runtime requirements supported by repository metadata?
- [ ] Are component relationships described accurately?
- [ ] Are links valid or at least derived from real repository paths?
- [ ] Are there no invented benchmarks, claims, compatibility guarantees, or features?

## Copy quality

- [ ] Is the tagline precise rather than promotional?
- [ ] Are component descriptions one or two lines at most?
- [ ] Are unsupported superlatives removed?
- [ ] Is terminology consistent across the page?
- [ ] Are paragraphs short and scannable?

## Installation

- [ ] Is one recommended installation method visually primary?
- [ ] Are secondary methods folded or moved lower?
- [ ] Can the primary command be copied directly?
- [ ] Is the post-install action clear?

## Architecture

- [ ] Does the architecture section explain the real project shape?
- [ ] Are natural layers / package boundaries visible?
- [ ] Are arrows used only for real dependencies or flows?
- [ ] Are independent components not falsely depicted as dependent?

## Scope

- [ ] Is the root README an entry point rather than a reference manual?
- [ ] Are package-specific details linked to package READMEs?
- [ ] Is long troubleshooting / configuration content moved to docs or `<details>`?

## Final impression

- [ ] Does this look like maintained developer tooling rather than a personal toolbox?
- [ ] Is it restrained rather than decorative?
- [ ] Would a new developer know what to do next?

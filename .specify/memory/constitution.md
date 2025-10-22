<!--
SYNC IMPACT REPORT
==================
Version Change: Initial → 1.0.0
Rationale: First constitution ratification with core Python development principles

Modified Principles: None (initial creation)
Added Sections:
  - Core Principles (5 principles focused on minimal Python code)
  - Code Quality Standards
  - Development Workflow
  - Governance

Removed Sections: None (initial creation)

Templates Requiring Updates:
  ✅ .specify/templates/plan-template.md - Constitution Check section aligned
  ✅ .specify/templates/spec-template.md - Requirements align with simplicity principles
  ✅ .specify/templates/tasks-template.md - Task structure supports incremental development

Follow-up TODOs: None
-->

# Hikvision Overlay Constitution

## Core Principles

### I. Minimal Code
Every line of code is a liability. Write the smallest amount of code that solves the problem completely.

**Rules:**
- MUST eliminate dead code, unused imports, and redundant abstractions
- MUST prefer standard library over external dependencies when functionality is equivalent
- MUST NOT add features or abstractions before they are needed (YAGNI)
- MUST justify any dependency addition with concrete technical need

**Rationale:** Less code means fewer bugs, easier maintenance, faster comprehension, and reduced technical debt. External dependencies introduce security risks, version conflicts, and maintenance burden.

### II. Readability First
Code is read far more often than it is written. Optimize for the reader, not the writer.

**Rules:**
- MUST use clear, descriptive names that reveal intent
- MUST write functions that do one thing and do it well (single responsibility)
- MUST keep functions short (ideally < 50 lines, maximum 100 lines)
- MUST prefer explicit over implicit: no magic, no clever tricks
- MUST include docstrings for all public functions and classes
- MUST use type hints for function signatures

**Rationale:** Code that is easy to read is easy to maintain, debug, and extend. Future maintainers (including your future self) will thank you.

### III. Standard Python Patterns
Follow established Python idioms and conventions. Don't reinvent the wheel.

**Rules:**
- MUST follow PEP 8 style guide
- MUST use standard library modules when available (e.g., `argparse`, `pathlib`, `dataclasses`)
- MUST follow Pythonic patterns (e.g., context managers, comprehensions, iterators)
- MUST NOT create custom frameworks or DSLs without exceptional justification
- SHOULD use proven third-party libraries for complex tasks (e.g., `requests` for HTTP)

**Rationale:** Standard patterns are familiar to all Python developers, reducing cognitive load and onboarding time. Well-maintained standard libraries are battle-tested and secure.

### IV. Simple Error Handling
Errors should be obvious, loud, and informative.

**Rules:**
- MUST fail fast with descriptive error messages
- MUST include context in error messages (what failed, why, what to do)
- MUST use specific exception types, not bare `except:`
- MUST log errors to stderr with sufficient detail for debugging
- MUST NOT silently swallow exceptions
- SHOULD validate inputs at system boundaries

**Rationale:** Clear error messages save hours of debugging. Fast failure prevents cascading errors and data corruption. Specific exceptions enable targeted error handling.

### V. Incremental Development
Build in small, tested, working increments. Never break the main branch.

**Rules:**
- MUST ensure code runs after every commit
- MUST write tests for new functionality (when tests are explicitly requested)
- MUST commit working code frequently (not giant batches)
- MUST use meaningful commit messages that explain "why"
- MUST NOT commit commented-out code or TODOs without issue references

**Rationale:** Small commits are easier to review, debug, and revert if needed. Working code at every step maintains project momentum and team confidence.

## Code Quality Standards

### Documentation Requirements
- All public functions and classes MUST have docstrings following Google or NumPy style
- Docstrings MUST include: description, Args, Returns, Raises (if applicable)
- Complex algorithms MUST include inline comments explaining the "why"
- README MUST include: purpose, installation, basic usage examples

### Testing Requirements (when explicitly requested)
- Tests MUST be written before or during implementation (TDD encouraged)
- Tests MUST be deterministic (no random data, no time dependencies)
- Tests MUST have clear names describing the scenario
- Tests MUST use standard testing libraries (pytest preferred)
- Integration tests REQUIRED for external API interactions

### Code Structure
- One class or closely related functions per file
- Maximum file length: 500 lines (if exceeded, refactor into modules)
- Group related functionality in modules/packages
- Keep flat structure when possible (avoid deep nesting)

### Formatting and Linting
- MUST use `black` for code formatting (line length: 100)
- MUST use `ruff` or `pylint` for linting
- MUST use `mypy` for type checking
- All checks MUST pass before commit

## Development Workflow

### Planning Before Coding
1. Understand the problem completely
2. Research existing solutions in the codebase
3. Design the simplest solution that could work
4. Write down the implementation plan in clear steps
5. Only then start coding

### Implementation Cycle
1. **Write** - Implement the smallest working piece
2. **Test** - Verify it works (manual or automated)
3. **Refactor** - Clean up while maintaining functionality
4. **Commit** - Save the working increment
5. **Repeat** - Move to next piece

### When Stuck (3-Attempt Rule)
After 3 failed attempts:
1. **STOP** - Do not try the same approach again
2. **Document** - Write down what failed and why
3. **Research** - Find alternative approaches (docs, existing code, Stack Overflow)
4. **Question** - Is this the right abstraction? Can it be simpler?
5. **Pivot** - Try a fundamentally different approach or ask for help

### Code Review Standards
- Changes MUST be reviewed before merging
- Reviewer MUST verify: readability, correctness, test coverage
- Reviewer MUST question complexity and suggest simpler alternatives
- Author MUST respond to all review comments

## Governance

### Constitution Authority
This constitution supersedes all other development practices and conventions. When in doubt, refer to these principles.

### Amendment Process
1. Propose amendment with rationale and impact analysis
2. Discuss with team/maintainers
3. Update constitution.md with incremented version
4. Update all dependent templates and documentation
5. Communicate changes to all contributors

### Compliance Verification
- All pull requests MUST be checked against these principles
- Any violation of "MUST" rules requires explicit justification
- Reviewers MAY reject changes that violate principles without justification
- Constitution violations found in existing code SHOULD be fixed incrementally

### Version Control
- Version format: MAJOR.MINOR.PATCH (semantic versioning)
- MAJOR: Backward-incompatible principle changes
- MINOR: New principles or substantial additions
- PATCH: Clarifications, wording fixes, typos

**Version**: 1.0.0 | **Ratified**: 2025-10-21 | **Last Amended**: 2025-10-21

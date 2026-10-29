# CLI Subcommand Registry Plan

## Design Overview

The goal is to refactor `shop/cli.py` from a single hardcoded command into a subcommand-based architecture using a registry pattern. This allows new commands (like `export`) and report formats to be added without modifying the CLI code itself.

### Core Design Pattern: Registry-Based Subcommands

1. **Registry Module**: A central registry (`cli/registry.py`) that maps subcommand names to their handler functions
2. **Handler Functions**: Each subcommand is a standalone function that knows its own arguments and behavior
3. **Dynamic Dispatch**: The CLI main function looks up the requested command in the registry and dispatches accordingly
4. **No Code Changes for New Commands**: Adding a new subcommand only requires registering it in the registry, not touching `cli.py`

---

## Step-by-Step Plan

### Phase 1: Foundation (Steps 1-3)

**Step 1: Create the registry module structure**
- Create `shop/cli/registry.py` with an empty dictionary or list of registered commands
- Define a standard interface for subcommand handlers (e.g., `def handler(argv): -> int`)
- Add documentation showing how to register new commands

**Step 2: Implement basic command registration mechanism**
- Create a `register()` function that adds commands to the registry
- Create a `get_command(name)` function that returns the handler or raises an error if not found
- Ensure the registry is importable and testable as a module

**Step 3: Refactor main() to use the registry**
- Replace the hardcoded command check with a registry lookup
- Pass remaining arguments to the selected handler
- Handle the "unknown command" case by raising an error or printing usage
- Keep the same return codes (0 for success, non-zero for errors)

### Phase 2: Implement Existing Subcommand (Step 4)

**Step 4: Migrate `summary` subcommand to use the registry**
- Create a new function `def summary(argv): -> int` that replicates current behavior
- Register `summary` in the registry with name `"summary"`
- Verify existing invocations (`python -m shop.cli summary orders.json`) still work exactly as before

### Phase 3: Add New Subcommand (Step 5)

**Step 5: Implement `export` subcommand**
- Create a new function `def export(argv): -> int` that handles export logic
- Register `export` in the registry with name `"export"`
- Test the new command works independently of `summary`

### Phase 4: Error Handling and UX (Steps 6-8)

**Step 6: Add comprehensive error handling**
- Handle missing commands gracefully with usage message
- Handle handler-specific errors (file not found, invalid arguments)
- Ensure consistent exit codes across all handlers

**Step 7: Add help/usage information**
- Implement a `--help` flag that lists all registered commands
- Optionally add `--help <command>` for command-specific help
- Document available subcommands in the registry module

**Step 8: Add logging/debugging support**
- Log which command was invoked (for debugging)
- Optionally log errors with context about which handler failed

### Phase 5: Verification and Testing (Steps 9-12)

**Step 9: Write unit tests for the registry**
- Test `register()` adds commands correctly
- Test `get_command()` returns correct handlers
- Test unknown command raises appropriate error

**Step 10: Write integration tests for subcommands**
- Test `summary` with valid orders file (regression test)
- Test `export` with valid input
- Test both commands fail gracefully with invalid inputs

**Step 11: Verify backward compatibility**
- Run all existing `summary` invocations and confirm identical output
- Check that no behavior has changed for existing users

**Step 12: Add documentation examples**
- Document how to add a new subcommand (registry entry)
- Document how to add a new report format (if applicable)
- Include example commands in README or docs

---

## Risks and Mitigations

### Risk 1: Breaking existing `summary` invocations
**Mitigation**: 
- Keep the exact same function signature for `summary`
- Ensure no changes to stdout output format
- Run full regression test suite before considering complete

### Risk 2: Registry becomes a single point of failure
**Mitigation**:
- Make registry functions pure and testable in isolation
- Consider lazy loading if registry grows large
- Document the registry as the source of truth for available commands

### Risk 3: Command name conflicts
**Mitigation**:
- Enforce unique command names at registration time
- Raise clear error if duplicate name is attempted
- Document naming conventions (lowercase, no special chars)

### Risk 4: Handler signature inconsistencies
**Mitigation**:
- Define a standard handler interface in the registry module
- Validate arguments passed to handlers
- Add type hints for better IDE support and documentation

### Risk 5: Testing complexity increases
**Mitigation**:
- Test each handler independently (no cross-dependencies)
- Use fixtures for test data
- Mock storage/report modules where appropriate

---

## Verification Checklist

After implementation, verify:

- [ ] `python -m shop.cli summary orders.json` produces identical output to before
- [ ] `python -m shop.cli --help` lists all available subcommands
- [ ] `python -m shop.cli unknown_command` shows usage message
- [ ] New subcommand (`export`) can be added without touching `cli.py`
- [ ] Registry module is importable and testable
- [ ] All existing tests still pass
- [ ] No changes to `shop/report.py` or `shop/storage.py` required for new commands

---

## Future Considerations

- **Plugin system**: Extend registry pattern to support external plugins
- **Configuration**: Allow command-specific configuration via environment variables
- **CLI framework integration**: Consider migrating to click/argparse if more features needed
- **Type safety**: Add type hints to handlers for better IDE support

# CLI Refactoring Plan: From Single Command to Subcommand Architecture

## Current State
- `shop/cli.py` has a single hardcoded `summary` command
- Direct invocation: `python -m shop.cli summary orders.json`
- No extensibility for new report formats without editing CLI code

## Design Goals
1. Support multiple subcommands (summary, export, and future ones)
2. Add new report formats without modifying CLI code
3. Maintain backward compatibility with existing `summary` invocations
4. Use a registry pattern for extensibility

## Architecture Overview

### 1. Create a Registry Module (`shop/registry.py`)
   - Define a `Registry` class that manages command handlers
   - Each command is registered with a name and handler function
   - Registry provides `get_command(name)` to retrieve handlers
   - Default command (fallback) for unknown commands

### 2. Refactor CLI to Use Registry (`shop/cli.py`)
   - Remove hardcoded command logic
   - Initialize registry with available commands
   - Parse subcommand from argv
   - Delegate to registry handler
   - Handle errors uniformly

### 3. Create Command Handler Functions
   - Extract `summary` logic into a standalone function
   - Create `export` command handler (placeholder for future)
   - Each handler receives (argv, registry) for context

### 4. Define Command Interface
   - Commands accept: `argv` (list of arguments), `registry` (for lookups)
   - Commands return: exit code (0 for success, non-zero for error)
   - Commands print to stdout/stderr as needed

### 5. Registry Registration Pattern
   - Commands register themselves via decorator or explicit registration
   - Example: `@registry.command("summary")` decorator
   - Allows new commands to be added in separate modules

### 6. Error Handling Strategy
   - CLI handles: missing arguments, file not found, unknown commands
   - Command handlers handle: data processing errors
   - Consistent error messages to stderr

### 7. Backward Compatibility
   - `summary` remains the first registered command
   - Same argv format: `summary orders.json`
   - Existing scripts/invocations work unchanged

## Step-by-Step Implementation Plan

### Step 1: Create Registry Module
1. Create `shop/registry.py`
2. Implement `Registry` class with:
   - `register(name, handler)` method
   - `get(name)` method returning handler or None
   - `default_handler` for unknown commands
3. Add docstring explaining the pattern

### Step 2: Refactor CLI to Use Registry
1. Modify `shop/cli.py` to:
   - Import `Registry` from `shop.registry`
   - Create registry instance
   - Register `summary` command (call existing logic)
   - Parse subcommand from argv[0]
   - Call registry.get(subcommand)
   - Handle None result (unknown command)
2. Remove hardcoded "summary" check
3. Add usage message for missing/unknown commands

### Step 3: Extract Summary Command Handler
1. Create `summary_command(argv, registry)` function
2. Move existing summary logic here
3. Handle file loading errors
4. Print result to stdout
5. Return exit code

### Step 4: Create Export Command Handler
1. Create `export_command(argv, registry)` function
2. Implement basic structure (placeholder)
3. Parse output format from argv if needed
4. Call appropriate report function
5. Write output to file or stdout
6. Return exit code

### Step 5: Add Future Commands (Design)
1. Create `monthly_command(argv, registry)` function
2. Call `report.monthly()` function
3. Format and display results
4. Register in CLI

### Step 6: Implement Registration Pattern
1. Add decorator `@registry.command(name)` to commands
2. Or use explicit registration in CLI init
3. Document both approaches

### Step 7: Add Help/Usage System
1. Create `--help` flag support
2. List available subcommands
3. Show usage for each command
4. Integrate with registry

### Step 8: Error Handling Improvements
1. Add file validation before processing
2. Add type checking for orders data
3. Add validation for required arguments
4. Consistent error messages

### Step 9: Testing Strategy
1. Test existing `summary` command (backward compat)
2. Test unknown command handling
3. Test missing file handling
4. Test missing argument handling
5. Test new `export` command
6. Test new `monthly` command

### Step 10: Documentation
1. Document registry pattern
2. Document command interface
3. Document how to add new commands
4. Update usage examples

## Risk Assessment

### Low Risk
- Backward compatibility: `summary` command unchanged behavior
- Error handling: existing error cases preserved
- File I/O: same storage module used

### Medium Risk
- Registry pattern: new abstraction layer
- Command handlers: need to match CLI expectations
- Exit codes: must be consistent

### Higher Risk
- Breaking changes: if CLI interface changes unexpectedly
- Performance: registry lookup overhead (negligible)
- Complexity: more code to maintain

## Mitigation Strategies

1. **Incremental rollout**: Add commands one at a time
2. **Comprehensive tests**: Test all paths before merging
3. **Documentation**: Clear docs for new developers
4. **Type hints**: Add type annotations for clarity
5. **Logging**: Add debug logging for troubleshooting

## Verification Plan

### 1. Unit Tests
- Test each command handler in isolation
- Test registry registration/unregistration
- Test error conditions

### 2. Integration Tests
- Test full CLI flow for each command
- Test backward compatibility with `summary`
- Test unknown command handling

### 3. Manual Testing
- Run existing scripts with `summary`
- Test new commands
- Test edge cases (empty files, malformed JSON)

### 4. Code Review
- Review registry pattern implementation
- Review error handling consistency
- Review documentation completeness

### 5. Performance Check
- Verify no significant slowdown
- Check memory usage

## Future Extensions

### Easy Additions
- New report formats (add function to report.py, register command)
- New output formats (JSON, CSV, XML)
- New file formats (CSV, XML)

### Medium Additions
- Interactive mode
- Batch processing
- API endpoints

### Complex Additions
- Database support
- Real-time updates
- Authentication

## Conclusion

This plan transforms a monolithic CLI into an extensible subcommand architecture using a registry pattern. The design maintains backward compatibility while enabling easy addition of new commands without modifying the CLI core.

Key benefits:
- **Extensibility**: New commands added via registry
- **Maintainability**: Clear separation of concerns
- **Testability**: Commands can be tested independently
- **Scalability**: Easy to add more commands

The implementation follows established patterns and minimizes risk through incremental changes and comprehensive testing.
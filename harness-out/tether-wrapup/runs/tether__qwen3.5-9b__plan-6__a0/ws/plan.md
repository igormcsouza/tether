# CLI Subcommand Refactoring Plan

## Overview
Transform `shop/cli.py` from a single-command CLI into a multi-command CLI using a registry pattern. This allows new report formats to be added without modifying the CLI code.

## Design Principles

1. **Registry Pattern**: Central registry that maps subcommand names to handler functions
2. **Backward Compatibility**: Existing `summary` invocations must continue to work
3. **Extensibility**: New subcommands can be added by registering functions without touching CLI code
4. **Consistency**: All subcommands follow the same interface and error handling

## Step-by-Step Implementation Plan

### 1. Define the Subcommand Interface
   - Create a protocol/interface for subcommand handlers
   - Define signature: `handler(argv: list) -> int`
   - Return values: 0 for success, non-zero for errors
   - Document expected behavior for each handler

### 2. Create the Registry Module
   - Create `shop/registry.py` (or extend existing CLI module)
   - Implement a `Registry` class with:
     - `register(name, handler)` method to add subcommands
     - `get(name)` method to retrieve handlers
     - `list()` method to show available subcommands
   - Initialize with default subcommands (summary, monthly)
   - Use a dictionary or similar structure for O(1) lookup

### 3. Refactor Existing Subcommands
   - Extract `summary` logic into a standalone function `summary_handler(argv)`
   - Extract `monthly` logic into a standalone function `monthly_handler(argv)`
   - Each handler should:
     - Parse arguments
     - Load data from storage
     - Generate report
     - Print output
     - Return appropriate exit code
   - Handle errors consistently (FileNotFoundError, etc.)

### 4. Implement the Registry-Based CLI
   - Create `main(argv)` function that:
     - Checks if argv is empty (no subcommand)
     - Looks up subcommand in registry
     - Calls the handler with argv
     - Returns handler's exit code
   - Implement "no subcommand" error handling
   - Implement "unknown subcommand" error handling

### 5. Add Help/Usage Display
   - When no subcommand provided, show available subcommands
   - Include brief description of each subcommand
   - Show usage syntax for each subcommand

### 6. Update report.py for Extensibility
   - Keep existing `summary()` and `monthly()` functions
   - Optionally add a `register_report(name, func)` pattern for report functions
   - Ensure report functions accept orders list and return structured data

### 7. Test Backward Compatibility
   - Verify `python -m shop.cli summary orders.json` still works
   - Test error cases (missing file, invalid JSON)
   - Test with no arguments (should show help)
   - Test with unknown subcommand (should show error)

### 8. Add New Subcommand Example
   - Create a new report function (e.g., `regional()` in report.py)
   - Register it in the registry
   - Test the new subcommand works without modifying CLI code

### 9. Error Handling Strategy
   - Standardize error messages across all subcommands
   - Use stderr for errors, stdout for output
   - Return consistent exit codes:
     - 0: Success
     - 1: File not found / I/O errors
     - 2: Usage errors / invalid arguments
     - 3: Unknown subcommand

### 10. Documentation
    - Document the registry pattern
    - Document how to add new subcommands
    - Document the handler interface
    - Add docstrings to all handler functions

## Risk Assessment

### Low Risk
- **Backward compatibility**: Existing `summary` command must work unchanged
- **Error handling**: Standardize on existing patterns
- **Testing**: Comprehensive tests before deployment

### Medium Risk
- **Registry design**: Need to ensure extensibility without tight coupling
- **Handler interface**: Must be flexible enough for future subcommands
- **Error consistency**: Different subcommands may have different error modes

### High Risk (Mitigated)
- **Breaking changes**: None planned - all changes additive
- **Performance**: Minimal impact, registry lookup is O(1)
- **Code complexity**: Slight increase, but well-structured

## Verification Strategy

### Unit Tests
1. Test each handler function in isolation
2. Test registry registration and retrieval
3. Test error cases for each handler

### Integration Tests
1. Test CLI with all existing subcommands
2. Test CLI with no arguments (help)
3. Test CLI with unknown subcommand
4. Test CLI with missing files
5. Test adding new subcommand without CLI changes

### Manual Testing
1. Run existing commands: `shop.cli summary orders.json`
2. Run new commands: `shop.cli monthly orders.json`
3. Test error cases
4. Test help output

### Code Review Checklist
- [ ] No changes to existing `summary` command behavior
- [ ] Registry is properly initialized
- [ ] Error handling is consistent
- [ ] New subcommands can be added without CLI changes
- [ ] All tests pass
- [ ] Documentation is complete

## Future Extensions

### Potential New Subcommands
- `export`: Export reports to different formats (CSV, XML, etc.)
- `filter`: Filter orders by criteria
- `aggregate`: More complex aggregations
- `compare`: Compare periods/regions

### Architecture Benefits
- **Separation of concerns**: CLI logic separate from business logic
- **Testability**: Handlers can be tested independently
- **Maintainability**: Easy to add new features
- **Discoverability**: Users can see available commands

## Timeline

1. **Phase 1**: Design and implement registry (1-2 days)
2. **Phase 2**: Refactor existing subcommands (1 day)
3. **Phase 3**: Implement CLI dispatcher (1 day)
4. **Phase 4**: Testing and validation (1-2 days)
5. **Phase 5**: Documentation (0.5 day)

Total estimated: 4-6 days

## Conclusion

This plan provides a clear, incremental path to transforming the CLI while maintaining backward compatibility and enabling future extensibility. The registry pattern is a well-established design that minimizes coupling and maximizes flexibility.
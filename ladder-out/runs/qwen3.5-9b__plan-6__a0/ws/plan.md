# CLI Refactoring Plan: Adding Subcommands with Registry Pattern

## Current State
- Single command: `shop.cli summary <file>`
- Direct `if/else` logic in `main()`
- Hardcoded command name and usage
- Adding new commands requires editing `cli.py`

## Design Goals
1. Support multiple subcommands (summary, export, and future ones)
2. Add new report formats without modifying CLI code
3. Maintain backward compatibility with existing `summary` invocations
4. Clean separation of concerns

## Step-by-Step Plan

### 1. Define a Command Registry Interface
   - Create a `Command` base class or protocol with:
     - `name`: string identifier for the subcommand
     - `func`: callable that takes `(orders, argv)` and returns exit code
     - `help_text`: optional description for `--help`
   - This interface allows any report function to be registered as a command

### 2. Create a Registry Class
   - Implement a `CommandRegistry` class that:
     - Stores commands in a dictionary keyed by name
     - Provides `register(name, func)` method for adding commands
     - Provides `get(name)` method to retrieve commands
     - Provides `list()` method to show available commands
   - Initialize with default commands (summary, export)

### 3. Refactor Report Functions to Be Command-Compatible
   - Modify existing `summary()` in `report.py` to accept optional `argv` parameter
   - Create new `export()` function that:
     - Takes orders and output format/type
     - Returns exit code (0 for success, non-zero for errors)
     - Prints appropriate output
   - Design functions to work with the registry pattern

### 4. Implement the Export Command
   - Add `export()` function to `report.py`:
     - Parse output format from argv (e.g., "csv", "json", "html")
     - Convert orders to specified format
     - Print or save to file
     - Return appropriate exit code
   - Register this as a new subcommand

### 5. Refactor CLI Main Function
   - Replace hardcoded `if/else` with registry lookup:
     ```python
     registry = CommandRegistry()
     registry.register("summary", report.summary)
     registry.register("export", report.export)
     
     if len(argv) != 2 or argv[0] not in registry:
         print usage, return error
     ```
   - Call `registry.get(argv[0])(orders, argv[1:])`
   - This eliminates the need to edit CLI code for new commands

### 6. Add --help Support
   - Implement `--help` flag parsing in CLI
   - Show available subcommands via `registry.list()`
   - Show individual command help via `--help` on subcommand

### 7. Backward Compatibility Verification
   - Test that `shop.cli summary orders.json` still works exactly as before
   - Verify error handling (missing file, wrong arguments) unchanged
   - Ensure exit codes remain consistent

### 8. Extensibility Verification
   - Add a new command (e.g., `daily`) to `report.py`
   - Register it in the registry
   - Verify it works without modifying `cli.py`
   - Test that `--help` shows the new command

### 9. Error Handling Improvements
   - Centralize error messages in registry or CLI layer
   - Add consistent error handling for:
     - Unknown subcommands
     - Missing arguments
     - File not found
     - Invalid output formats

### 10. Documentation
   - Document the registry pattern in docstrings
   - Add examples of how to add new commands
   - Update usage examples

## Risk Assessment

### Low Risk
- Existing `summary` command behavior unchanged
- Backward compatibility maintained
- Simple registry pattern, well-understood

### Medium Risk
- Export function implementation complexity
- Need to handle multiple output formats correctly
- Error handling consistency across commands

### High Risk (Mitigated)
- Breaking existing invocations (avoided by design)
- Performance impact (minimal, just dictionary lookup)

## Verification Strategy

### Unit Tests
1. Test each command function independently
2. Test registry registration and retrieval
3. Test error cases (missing file, unknown command)

### Integration Tests
1. Test full CLI invocation for each command
2. Test backward compatibility with `summary`
3. Test new `export` command with different formats
4. Test `--help` functionality

### Manual Testing
1. Run existing commands: `shop.cli summary orders.json`
2. Run new commands: `shop.cli export orders.json --format csv`
3. Test error cases: `shop.cli unknown orders.json`
4. Test help: `shop.cli --help`, `shop.cli summary --help`

## Implementation Order

1. **Phase 1**: Create CommandRegistry class (no code changes to report.py)
2. **Phase 2**: Refactor CLI to use registry (minimal changes)
3. **Phase 3**: Implement export command in report.py
4. **Phase 4**: Register all commands
5. **Phase 5**: Add --help support
6. **Phase 6**: Testing and verification

## Future Extensions

The registry pattern enables easy addition of:
- `daily` - Daily revenue breakdown
- `regional` - Revenue by region
- `top_customers` - Top spending customers
- `export` variants (csv, json, html, xml)

All future commands only require:
1. Adding a function to `report.py`
2. Registering it in the registry
3. No CLI code changes needed
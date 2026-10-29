# CLI Subcommand Registry Plan

## Design Overview

The current CLI is a simple monolithic script with a single `summary` command. The goal is to refactor it into a subcommand-based architecture with a registry pattern that allows new commands to be added without modifying the CLI code.

### Key Principles

1. **Registry Pattern**: Commands are registered in a central registry, allowing dynamic discovery and addition
2. **Backward Compatibility**: Existing `summary` invocations must continue to work
3. **Extensibility**: New commands (export, and future ones) can be added by registering them
4. **Separation of Concerns**: CLI logic is separated from command implementations

## Implementation Steps

### 1. Create Command Registry Module

- Create `shop/registry.py` with a `CommandRegistry` class
- The registry will store command functions with their names and descriptions
- Provide methods: `register(name, func, description)`, `get(name)`, `list()`
- Include a default registry instance that can be imported

### 2. Define Command Interface

- Create `shop/commands.py` with a base `Command` class or protocol
- Define the interface: `name`, `description`, `func(orders, args)`
- Each command will be a callable that takes orders data and optional arguments

### 3. Implement Summary Command

- Create `shop/commands/summary.py`
- Extract the existing summary logic into this module
- The command function should return formatted output or structured data

### 4. Implement Export Command

- Create `shop/commands/export.py`
- Support exporting orders in various formats (JSON, CSV, etc.)
- Include format selection via arguments

### 5. Refactor CLI to Use Registry

- Modify `shop/cli.py` to:
  - Import the registry
  - Register default commands (summary, export)
  - Parse subcommand from argv
  - Look up command in registry
  - Execute command with appropriate arguments
  - Handle unknown commands gracefully

### 6. Create Command Factory/Loader

- Implement a loader that can discover commands from modules
- Support both explicit registration and automatic discovery
- Allow commands to be added via plugins or configuration

### 7. Add Help/Usage System

- Implement `--help` flag that lists all registered commands
- Show command descriptions and available options
- Display usage examples for each command

### 8. Add Argument Parsing

- Implement argument parsing for each command
- Support common patterns: `--format`, `--output`, etc.
- Use a lightweight parser or argparse per command

### 9. Implement Error Handling

- Standardize error messages across commands
- Handle missing files, invalid arguments, command not found
- Return appropriate exit codes

### 10. Add Future Command Hooks

- Create a mechanism for adding commands without code changes
- Support plugin system or configuration-based registration
- Allow external modules to register commands

## Sequencing

1. **Phase 1: Foundation**
   - Step 1: Create registry module
   - Step 2: Define command interface
   - Step 3: Implement summary command

2. **Phase 2: CLI Refactor**
   - Step 4: Refactor CLI to use registry
   - Step 5: Implement export command
   - Step 6: Create command loader

3. **Phase 3: Polish**
   - Step 7: Add help system
   - Step 8: Add argument parsing
   - Step 9: Implement error handling

4. **Phase 4: Extensibility**
   - Step 10: Add future command hooks
   - Test plugin system

## Risks

### 1. Backward Compatibility
- **Risk**: Existing `summary orders.json` invocations break
- **Mitigation**: Ensure summary command is registered first and tested thoroughly
- **Mitigation**: Keep exact same output format for summary

### 2. Registry Performance
- **Risk**: Registry lookup becomes slow with many commands
- **Mitigation**: Use dict-based storage (O(1) lookup)
- **Mitigation**: Cache command lookups if needed

### 3. Command Discovery Complexity
- **Risk**: Automatic discovery becomes too complex
- **Mitigation**: Start with explicit registration, add discovery later
- **Mitigation**: Document registration process clearly

### 4. Argument Parsing Inconsistency
- **Risk**: Different commands use different argument styles
- **Mitigation**: Define a standard argument interface
- **Mitigation**: Use consistent naming conventions

### 5. Error Handling Gaps
- **Risk**: Some commands don't handle errors properly
- **Mitigation**: Create base error classes
- **Mitigation**: Add error handling to each command

### 6. Plugin Security
- **Risk**: External plugins could introduce vulnerabilities
- **Mitigation**: Validate plugin code before loading
- **Mitigation**: Use importlib with sandboxing if needed

### 7. Testing Complexity
- **Risk**: Testing all command combinations is difficult
- **Mitigation**: Use pytest with fixtures for each command
- **Mitigation**: Mock storage and report modules

## Verification Plan

### 1. Backward Compatibility Tests

```bash
# Test existing summary command
python -m shop.cli summary orders.json
# Should produce identical output to before

# Test with non-existent file
python -m shop.cli summary nonexistent.json
# Should show "no such file" error

# Test with no arguments
python -m shop.cli
# Should show usage message
```

### 2. New Command Tests

```bash
# Test export command
python -m shop.cli export orders.json --format json
python -m shop.cli export orders.json --format csv

# Test help
python -m shop.cli --help
# Should list summary and export commands

# Test unknown command
python -m shop.cli unknown orders.json
# Should show "command not found" error
```

### 3. Registry Tests

```python
# Test registry operations
from shop.registry import registry

# Check registration
registry.register("test", func, "Test command")
assert "test" in registry.list()

# Check lookup
cmd = registry.get("test")
assert cmd is not None

# Check default commands
assert "summary" in registry.list()
assert "export" in registry.list()
```

### 4. Integration Tests

- Test each command with real order data
- Test error conditions for each command
- Test argument parsing for each command
- Test help output for each command

### 5. Performance Tests

- Measure command lookup time with many commands
- Measure startup time with registry
- Ensure no significant performance regression

### 6. Code Quality Checks

- Run linters on all new code
- Ensure type hints are consistent
- Check for code duplication
- Verify documentation is complete

### 7. Documentation Verification

- Verify --help shows all commands
- Verify command descriptions are accurate
- Verify usage examples work

### 8. Future-Proofing Tests

- Test adding a new command without modifying CLI
- Test plugin registration mechanism
- Verify new command appears in help

## Summary

This plan provides a clear path from the current monolithic CLI to a subcommand-based architecture with a registry pattern. The key is to maintain backward compatibility while building in extensibility from the start. Each phase builds on the previous one, and verification is built in at each step to catch issues early.

The registry pattern ensures that new commands can be added by simply registering them, without touching the CLI code. This makes the CLI maintainable and extensible for future requirements.

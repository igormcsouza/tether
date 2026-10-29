# CLI Subcommand Registry Plan

## Design Overview

The goal is to refactor `shop/cli.py` from a single hardcoded command (`summary`) into a subcommand architecture using a registry pattern. This allows:
- Adding new report formats (e.g., `export`, `details`) without modifying the CLI code
- Extending functionality through plugins or future commands
- Maintaining backward compatibility with existing `summary` invocations

## Key Components

1. **Registry Pattern**: A central registry that maps command names to their handler functions
2. **Handler Functions**: Each report format becomes a standalone function in `shop/report.py` (or a new module)
3. **CLI Entry Point**: The main entry point dispatches based on the subcommand argument

## Design Decisions

### 1. Registry Location
- **Option A**: Keep registry in `cli.py` with handlers imported from `report.py`
  - Pros: Simple, all logic in one place
  - Cons: Report functions still tightly coupled to CLI
- **Option B**: Move registry to a new `shop/commands.py` module
  - Pros: Decouples CLI from report logic, easier to test commands independently
  - Cons: Slightly more modules
- **Decision**: Option B for better separation of concerns

### 2. Handler Signature
- All handlers should accept the same arguments (e.g., `orders`) and return structured data
- This allows consistent processing pipeline: load → process → output format

### 3. Output Format
- Handlers return Python objects (dicts, lists)
- CLI determines how to serialize based on command type
- Future: Could support JSON output for `export` command

## Sequencing

### Phase 1: Foundation
1. Create `shop/commands.py` with a simple registry structure
2. Implement the `summary` handler in `report.py` (already exists, but ensure it's importable)
3. Update `cli.py` to use the registry pattern
4. Test that existing `python -m shop.cli summary orders.json` still works

### Phase 2: Export Command
1. Create `export` handler in `report.py` (or new module)
2. Add `export` to the registry in `commands.py`
3. Implement output formatting for export command
4. Test `python -m shop.cli export orders.json`

### Phase 3: Future Extensions
1. Design pattern for adding new commands without code changes
2. Document how to add new report formats
3. Consider plugin architecture for truly extensible system

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Breaking existing `summary` command | High | Test thoroughly; ensure backward compatibility is verified |
| Registry pattern complexity | Medium | Start simple, document clearly, keep registry minimal |
| Handler signature inconsistency | Medium | Enforce consistent signatures via type hints or runtime checks |
| Import errors during development | Low | Use try/except in CLI with clear error messages |

## Verification Strategy

### 1. Existing Functionality Test
```bash
python -m shop.cli summary orders.json
# Should output: "X orders, revenue Y.YY"
```

### 2. New Command Test
```bash
python -m shop.cli export orders.json
# Should output formatted JSON or similar
```

### 3. Error Handling Test
```bash
python -m shop.cli nonexistent orders.json
# Should print usage error to stderr and exit with code 2
```

### 4. Registry Inspection
```bash
python -c "from shop.commands import registry; print(list(registry.keys()))"
# Should show all registered commands
```

## Implementation Steps (Numbered)

1. **Create `shop/commands.py`**
   - Define a simple registry structure: `registry = {"summary": summary_handler, ...}`
   - Add helper function to dispatch based on command name

2. **Update `shop/report.py`**
   - Ensure `summary` is properly defined and importable
   - Create `export` handler (or other future handlers)
   - Consider adding type hints for clarity

3. **Refactor `shop/cli.py`**
   - Remove hardcoded command check
   - Import registry from `commands.py`
   - Use registry to dispatch based on first argument
   - Handle errors gracefully with clear messages

4. **Test Existing Command**
   - Verify `summary` still works exactly as before
   - Ensure output format is identical

5. **Test New Commands**
   - Test `export` command
   - Verify error handling for unknown commands

6. **Document the Pattern**
   - Add comments explaining how to add new commands
   - Document expected handler signatures

7. **Add Type Hints (Optional but Recommended)**
   - Use `typing` module for better IDE support and documentation
   - Helps catch signature mismatches early

## Future Considerations

- **Plugin System**: Could allow external modules to register commands
- **Configuration**: Allow customizing output formats per command
- **Logging**: Add logging instead of print statements for better observability
- **Validation**: Add input validation before processing orders
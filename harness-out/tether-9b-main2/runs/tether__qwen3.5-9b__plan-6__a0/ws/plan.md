# CLI Refactoring Plan: From Single Command to Subcommands with Registry

## Current State
- Single `summary` command hardcoded in `cli.py`
- Report functions exist in `report.py` but are not exposed as CLI subcommands
- No extensibility mechanism for new report formats

## Design Goals
1. Maintain backward compatibility with existing `summary` invocations
2. Enable easy addition of new report formats without modifying CLI code
3. Support multiple subcommands (summary, export, and future ones)
4. Keep code modular and testable

## Step-by-Step Plan

### 1. Define the Registry Interface
   - Create a `registry.py` module with a `Registry` class
   - Define a `Command` base class or protocol with required attributes:
     - `name`: string identifier for the subcommand
     - `func`: callable that takes orders and returns data
     - `description`: human-readable description
   - Implement `register()` method to add commands to the registry
   - Implement `get(name)` method to retrieve commands by name
   - Implement `list()` method to enumerate all registered commands

### 2. Refactor Report Functions into Command Objects
   - Modify `report.py` to create command objects for each report function
   - Each command object wraps a report function with metadata
   - Example:
     ```python
     summary_cmd = Command(
         name="summary",
         func=summary,
         description="Show order count and total revenue"
     )
     ```
   - Export these command objects from `report.py`

### 3. Create a Default Registry Module
   - Create `shop/registry.py` that imports and registers all default commands
   - This module will be the single source of truth for available commands
   - Commands can be registered at module load time or via explicit registration

### 4. Refactor CLI to Use the Registry
   - Modify `cli.py` to:
     - Import the registry
     - Parse the first argument as the subcommand name
     - Look up the command in the registry
     - Execute the command's function with the orders data
     - Handle unknown commands gracefully
   - Keep the exact same behavior for `summary` subcommand

### 5. Implement Output Formatting
   - Create a `format.py` module with formatting functions
   - Each command can specify its preferred output format
   - Default to JSON for extensibility, but support text formats
   - Commands can override default formatting

### 6. Add the Export Subcommand
   - Create an `export` command in `report.py`
   - This command should serialize orders to a specified format (JSON, CSV, etc.)
   - Register it in the default registry
   - CLI will automatically expose it as `shop.cli export ORDERS.json [OPTIONS]`

### 7. Implement Error Handling and Exit Codes
   - Standardize error handling across all commands
   - Return appropriate exit codes:
     - 0: Success
     - 1: File not found or invalid input
     - 2: Usage error or unknown command
   - Provide helpful error messages

### 8. Add Help/Usage Display
   - Implement `--help` flag that shows:
     - Available subcommands
     - Brief description of each
     - Usage examples
   - Each command can have its own `--help` that shows specific options

### 9. Create Extension Mechanism
   - Design a way for external code to register custom commands
   - Support:
     - Command registration via import hooks
     - Plugin system for third-party commands
     - Environment variable or config file for custom commands
   - Ensure new commands don't break existing functionality

### 10. Testing Strategy
   - Write unit tests for:
     - Registry operations (register, get, list)
     - Each report function
     - CLI parsing and command dispatch
     - Error handling scenarios
   - Test backward compatibility:
     - Existing `summary orders.json` must work identically
     - All existing invocations must produce same output
   - Test new functionality:
     - `export` command works correctly
     - Unknown commands return proper error
     - Help displays correctly

### 11. Risk Assessment
   - **Risk 1: Breaking existing invocations**
     - Mitigation: Test all existing command patterns before and after
     - Mitigation: Keep exact same output format for summary
   
   - **Risk 2: Performance overhead from registry lookup**
     - Mitigation: Use dictionary for O(1) lookup, not list iteration
     - Mitigation: Cache registry after initialization
   
   - **Risk 3: Complexity creep**
     - Mitigation: Start with minimal viable implementation
     - Mitigation: Document each step clearly
   
   - **Risk 4: Error handling inconsistencies**
     - Mitigation: Define clear error handling contract
     - Mitigation: Test all error paths
   
   - **Risk 5: Future commands breaking existing ones**
     - Mitigation: Commands are isolated; one failure shouldn't affect others
     - Mitigation: Registry lookup is defensive

### 12. Sequencing and Dependencies
   - Phase 1: Registry interface and default commands (steps 1-3)
   - Phase 2: CLI refactoring (step 4)
   - Phase 3: Output formatting (step 5)
   - Phase 4: Export command (step 6)
   - Phase 5: Error handling and help (steps 7-8)
   - Phase 6: Extension mechanism (step 9)
   - Phase 7: Comprehensive testing (step 10)

### 13. Verification Plan
   - **Before refactoring:**
     - Run `python -m shop.cli summary orders.json`
     - Capture exact output
   
   - **After refactoring:**
     - Run identical command, verify identical output
     - Run `python -m shop.cli --help` to verify help works
     - Run `python -m shop.cli export orders.json` to verify new command
     - Run `python -m shop.cli unknown` to verify error handling
     - Run `python -m shop.cli` (no args) to verify usage message
   
   - **Regression tests:**
     - Test with various order files
     - Test with empty files
     - Test with malformed JSON
     - Test with missing files

### 14. Future Extensions
   - Add `filter` subcommand to filter orders by criteria
   - Add `aggregate` subcommand for complex aggregations
   - Add `compare` subcommand to compare two order sets
   - Each new command follows the same pattern:
     1. Define function in `report.py`
     2. Create Command object
     3. Register in registry
     4. No CLI code changes needed

## Summary of Changes

### Files to Create/Modify:
1. `shop/registry.py` (new) - Registry implementation
2. `shop/report.py` (modify) - Add Command objects
3. `shop/cli.py` (modify) - Use registry instead of hardcoded logic
4. `shop/format.py` (new) - Output formatting utilities
5. `shop/__init__.py` (modify) - Export registry and commands

### Key Design Decisions:
- Registry is a simple dictionary-based lookup for performance
- Commands are first-class objects with metadata
- Output formatting is separate from data processing
- Extension mechanism is built-in, not plugin-based for simplicity
- Backward compatibility is the highest priority

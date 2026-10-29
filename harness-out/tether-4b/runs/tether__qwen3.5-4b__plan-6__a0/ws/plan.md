# Plan: Implement Subcommand Registry Pattern in shop/cli.py

## Design Overview

Replace the hardcoded `summary` command with a subcommand system using a registry pattern. The registry will map subcommand names to handler functions, allowing new report formats (like `export`) to be added without modifying the CLI code.

### Key Components:
1. **Registry**: A dictionary mapping subcommand names to their handler functions
2. **Handler Functions**: Each report format becomes a function that takes orders and returns structured data
3. **CLI Entry Point**: Updated `main()` to dispatch based on subcommand name

## Step-by-Step Plan

1. **Define the registry structure**
   - Create a global registry dictionary in cli.py
   - Initialize it with known subcommands: `summary` and `export`
   - Each entry maps command name → handler function reference

2. **Create handler functions for each report format**
   - Move existing `report.summary()` logic into a new `cli.handler_summary()` function
   - Create `cli.handler_export()` that accepts orders and returns export data
   - Keep `report.py` unchanged (or optionally move handlers there if desired)

3. **Update main() to use the registry**
   - Parse command name from argv[0]
   - Look up handler in registry; print usage error if not found
   - Call appropriate handler with orders data
   - Print formatted output based on handler return value

4. **Ensure backward compatibility**
   - Existing `python -m shop.cli summary orders.json` must work unchanged
   - The `summary` subcommand must be registered first
   - Output format should match current behavior exactly

5. **Add export subcommand**
   - Register `export` in the registry
   - Implement handler that writes orders to a file or other format
   - Handle command-line arguments for output path

6. **Document usage**
   - Print help message when no subcommand provided
   - Document available subcommands in usage string

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Breaking existing `summary` invocations | Keep `summary` registered first; test with exact same command |
| Missing subcommand handling | Add clear error message when unknown subcommand is used |
| Handler function signature changes | Use consistent signature: `handler(orders, **kwargs)` |
| Registry initialization order | Initialize registry at module import time (before main()) |
| Export format flexibility | Design handler to accept output path as optional argument |

## Verification Steps

1. Run existing command: `python -m shop.cli summary orders.json` → should print count and revenue
2. Run new command: `python -m shop.cli export orders.json output.json` → should export data
3. Test unknown subcommand: `python -m shop.cli unknown orders.json` → should show usage error
4. Verify registry is extensible: Add new handler, register it, run without CLI changes

## Future Extensions

- Add more subcommands (e.g., `monthly`, `stats`) by registering them in the same way
- Support command-line options via argparse or similar pattern
- Move registry to a separate module for better organization
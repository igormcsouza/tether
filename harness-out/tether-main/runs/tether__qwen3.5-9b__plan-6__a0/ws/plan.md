# CLI Refactoring Plan: From Single Command to Subcommand Registry

## Current State
- Single `main()` function in `shop/cli.py`
- Hard-coded "summary" command
- Direct calls to `report.summary()`
- No extensibility for new report formats

## Design Goals
1. Support multiple subcommands (summary, export, and future ones)
2. Add new report formats without editing CLI code
3. Maintain backward compatibility with existing "summary" invocations
4. Clean separation of concerns

## Architecture

### 1. Registry Pattern
Create a registry that maps subcommand names to handler functions. This allows:
- Dynamic registration of new commands
- No CLI code changes needed for new formats
- Easy testing and mocking

### 2. Subcommand Structure
Each subcommand will be a function that:
- Takes orders data as input
- Returns a result (dict, string, or exit code)
- Handles its own error cases

### 3. CLI Entry Point
The `main()` function will:
- Parse subcommand from argv
- Look up handler in registry
- Call handler with appropriate arguments
- Handle errors and exit codes

## Implementation Steps

### Step 1: Create Registry Module
**File:** `shop/registry.py`

```python
"""Registry for subcommand handlers."""

from typing import Dict, Callable, Any

class Registry:
    """Registry for subcommand handlers."""
    
    def __init__(self):
        self._handlers: Dict[str, Callable] = {}
    
    def register(self, name: str, handler: Callable) -> None:
        """Register a subcommand handler."""
        self._handlers[name] = handler
    
    def get(self, name: str) -> Callable:
        """Get a handler by name."""
        try:
            return self._handlers[name]
        except KeyError:
            raise ValueError(f"unknown subcommand: {name}")
    
    def list_commands(self) -> list:
        """Return list of registered command names."""
        return list(self._handlers.keys())


# Global registry instance
registry = Registry()
```

### Step 2: Create Base Handler Interface
**File:** `shop/handlers.py`

```python
"""Base handler interface and utilities."""

from typing import Dict, Any, Optional
from shop import storage


class HandlerError(Exception):
    """Base exception for handler errors."""
    pass


class FileError(HandlerError):
    """File-related errors."""
    pass


def load_orders(path: str) -> list:
    """Load orders from file."""
    try:
        return storage.load_orders(path)
    except FileNotFoundError:
        raise FileError(f"no such file: {path}")
    except json.JSONDecodeError:
        raise FileError(f"invalid JSON: {path}")
    except Exception as e:
        raise FileError(f"error loading {path}: {e}")
```

### Step 3: Create Summary Handler
**File:** `shop/handlers/summary.py`

```python
"""Summary report handler."""

from typing import List, Dict, Any
from shop.handlers import HandlerError, load_orders
from shop import report


def handle(argv: list) -> int:
    """Handle summary subcommand.
    
    Args:
        argv: List of arguments (path to orders file)
    
    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    if len(argv) != 1:
        print("usage: shop.cli summary ORDERS.json", file=sys.stderr)
        return 2
    
    try:
        orders = load_orders(argv[0])
    except FileError as e:
        print(str(e), file=sys.stderr)
        return 1
    
    s = report.summary(orders)
    print(f"{s['count']} orders, revenue {s['revenue']:.2f}")
    return 0
```

### Step 4: Create Export Handler
**File:** `shop/handlers/export.py`

```python
"""Export report handler."""

import json
from typing import List, Dict, Any
from shop.handlers import HandlerError, load_orders
from shop import report


def handle(argv: list) -> int:
    """Handle export subcommand.
    
    Args:
        argv: List of arguments (path to orders file, output format)
    
    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    if len(argv) != 2:
        print("usage: shop.cli export ORDERS.json FORMAT", file=sys.stderr)
        return 2
    
    try:
        orders = load_orders(argv[0])
    except FileError as e:
        print(str(e), file=sys.stderr)
        return 1
    
    format_name = argv[1].lower()
    
    if format_name == "json":
        output = json.dumps(report.summary(orders), indent=2)
    elif format_name == "csv":
        output = _to_csv(orders)
    elif format_name == "monthly":
        output = json.dumps(report.monthly(orders), indent=2)
    else:
        print(f"unknown format: {format_name}", file=sys.stderr)
        return 1
    
    print(output)
    return 0


def _to_csv(orders: List[Dict]) -> str:
    """Convert orders to CSV format."""
    if not orders:
        return "id,date,region,total\n"
    
    lines = ["id,date,region,total"]
    for o in orders:
        lines.append(f"{o['id']},{o['date']},{o['region']},{o['total']}")
    return "\n".join(lines)
```

### Step 5: Create Future Handler Template
**File:** `shop/handlers/template.py`

```python
"""Template for new report handlers."""

from typing import List, Dict, Any
from shop.handlers import HandlerError, load_orders


def handle(argv: list) -> int:
    """Handle <command> subcommand.
    
    Args:
        argv: List of arguments
    
    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    # Validate arguments
    if len(argv) != 1:
        print(f"usage: shop.cli <command> ORDERS.json", file=sys.stderr)
        return 2
    
    # Load orders
    try:
        orders = load_orders(argv[0])
    except FileError as e:
        print(str(e), file=sys.stderr)
        return 1
    
    # Generate report
    # result = report.<your_function>(orders)
    
    # Output result
    # print(result)
    
    return 0
```

### Step 6: Refactor CLI Entry Point
**File:** `shop/cli.py`

```python
"""Command line interface with subcommand registry."""

import sys
from typing import List, Optional

from shop import registry
from shop.handlers import load_orders, FileError


def main(argv: Optional[List[str]] = None) -> int:
    """Main entry point.
    
    Args:
        argv: Command line arguments (optional, uses sys.argv if None)
    
    Returns:
        Exit code
    """
    args = list(sys.argv[1:] if argv is None else argv)
    
    if not args:
        print("usage: shop.cli <command> [args...]", file=sys.stderr)
        print("commands:", ", ".join(registry.list_commands()), file=sys.stderr)
        return 1
    
    subcommand = args[0]
    handler_args = args[1:]
    
    try:
        handler = registry.get(subcommand)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        print("usage: shop.cli <command> [args...]", file=sys.stderr)
        print("commands:", ", ".join(registry.list_commands()), file=sys.stderr)
        return 1
    
    try:
        return handler(handler_args)
    except FileError as e:
        print(str(e), file=sys.stderr)
        return 1
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
```

### Step 7: Update Report Module (Optional)
**File:** `shop/report.py`

```python
"""Order reports. An order is {"id", "date": "YYYY-MM-DD", "region", "total"}."""

from typing import List, Dict


def summary(orders: List[Dict]) -> Dict[str, float]:
    """Generate summary report."""
    return {"count": len(orders), "revenue": round(sum(o["total"] for o in orders), 2)}


def monthly(orders: List[Dict]) -> Dict[str, float]:
    """Revenue per month, keyed "YYYY-MM"."""
    out = {}
    for o in orders:
        key = o["date"][:7]
        out[key] = round(out.get(key, 0) + o["total"], 2)
    return out


def export_json(orders: List[Dict]) -> str:
    """Export as JSON."""
    import json
    return json.dumps(summary(orders), indent=2)


def export_csv(orders: List[Dict]) -> str:
    """Export as CSV."""
    if not orders:
        return "id,date,region,total\n"
    
    lines = ["id,date,region,total"]
    for o in orders:
        lines.append(f"{o['id']},{o['date']},{o['region']},{o['total']}")
    return "\n".join(lines)
```

### Step 8: Registration in CLI
**File:** `shop/cli.py` (add after imports)

```python
# Register handlers
from shop.handlers import summary, export
registry.register("summary", summary)
registry.register("export", export)
```

### Step 9: Create Handler Factory (Optional Enhancement)
**File:** `shop/handlers/factory.py`

```python
"""Handler factory for dynamic handler creation."""

from typing import Dict, Callable, Any, Type
from shop import report


class HandlerFactory:
    """Factory for creating handlers dynamically."""
    
    def __init__(self, registry):
        self.registry = registry
    
    def create_handler(self, name: str, func: Callable) -> Callable:
        """Create a handler with error handling."""
        def wrapped_handler(argv: list) -> int:
            try:
                return func(argv)
            except Exception as e:
                print(f"error: {e}", file=sys.stderr)
                return 1
        return wrapped_handler
```

### Step 10: Add New Handler Without CLI Changes
**Example:** Create `shop/handlers/detailed.py`

```python
"""Detailed report handler."""

from typing import List, Dict
from shop.handlers import HandlerError, load_orders
from shop import report


def handle(argv: list) -> int:
    """Handle detailed subcommand."""
    if len(argv) != 1:
        print("usage: shop.cli detailed ORDERS.json", file=sys.stderr)
        return 2
    
    try:
        orders = load_orders(argv[0])
    except FileError as e:
        print(str(e), file=sys.stderr)
        return 1
    
    # Generate detailed report
    detailed = report.detailed(orders)  # New function in report.py
    
    for order in detailed:
        print(order)
    
    return 0
```

**Register it:**
```python
# In shop/cli.py
from shop.handlers import detailed
registry.register("detailed", detailed)
```

**No CLI code changes needed!**

## Sequencing

1. **Phase 1: Foundation**
   - Create `registry.py`
   - Create `handlers.py` with base classes
   - Refactor `cli.py` to use registry

2. **Phase 2: Migration**
   - Create `handlers/summary.py` (copy of current logic)
   - Create `handlers/export.py` (new functionality)
   - Register both handlers
   - Test all existing functionality

3. **Phase 3: Enhancement**
   - Add new handlers (detailed, monthly, etc.)
   - Each new handler is just a new file + registration line

4. **Phase 4: Cleanup**
   - Remove old direct calls to report functions
   - Add comprehensive tests

## Risks and Mitigations

### Risk 1: Breaking Existing Invocations
**Mitigation:** 
- Keep "summary" as a registered handler with identical behavior
- Test all existing command patterns before and after
- Use semantic versioning for CLI

### Risk 2: Handler Complexity
**Mitigation:**
- Keep handlers simple and focused
- Use factory pattern for complex error handling
- Document handler interface clearly

### Risk 3: Registry Performance
**Mitigation:**
- Registry is small (dozens of handlers max)
- Lookup is O(1) with dict
- No performance concern

### Risk 4: Testing Overhead
**Mitigation:**
- Each handler is independently testable
- Mock storage layer
- Unit tests for each handler

### Risk 5: Error Handling Consistency
**Mitigation:**
- Define base exceptions in `handlers.py`
- Standard error message format
- Consistent exit codes

## Verification Plan

### 1. Unit Tests
```python
# test_registry.py
def test_register():
    registry.register("test", lambda: 0)
    assert registry.get("test")() == 0

def test_unknown_command():
    with pytest.raises(ValueError):
        registry.get("unknown")

# test_handlers.py
def test_summary_handler():
    result = summary.handle(["test.json"])
    assert result == 0

def test_export_handler():
    result = export.handle(["test.json", "json"])
    assert result == 0
```

### 2. Integration Tests
```python
# test_cli.py
def test_summary_command():
    # Test: python -m shop.cli summary orders.json
    result = main(["summary", "test.json"])
    assert result == 0

def test_export_command():
    # Test: python -m shop.cli export orders.json json
    result = main(["export", "test.json", "json"])
    assert result == 0

def test_unknown_command():
    result = main(["unknown"])
    assert result == 1
```

### 3. Backward Compatibility Tests
```python
def test_existing_summary_invocation():
    # Ensure exact same output as before
    orders = [{"id": 1, "total": 100}]
    old_output = f"{len(orders)} orders, revenue {sum(o['total'] for o in orders):.2f}"
    new_output = main(["summary", "test.json"])
    assert new_output == old_output
```

### 4. Stress Tests
- Test with 10,000 orders
- Test with invalid JSON
- Test with missing files
- Test with empty files

### 5. Performance Tests
- Benchmark handler creation vs direct calls
- Verify no performance regression
- Test registry lookup speed

## Future Extensions

### New Subcommands (No CLI Changes)
1. `shop.cli monthly ORDERS.json` - Monthly breakdown
2. `shop.cli detailed ORDERS.json` - Detailed order list
3. `shop.cli aggregate ORDERS.json` - Aggregated metrics
4. `shop.cli compare ORDERS.json FILE2.json` - Compare two files

### New Formats (No CLI Changes)
1. `shop.cli export ORDERS.json xml`
2. `shop.cli export ORDERS.json html`
3. `shop.cli export ORDERS.json csv`

### New Features
1. `shop.cli summary --format json` - JSON output
2. `shop.cli summary --verbose` - Verbose output
3. `shop.cli summary --output file.txt` - Write to file

All of these require only:
1. New handler function
2. Registration line in CLI
3. (Optional) New report function in report.py

## Summary

This plan transforms the CLI from a monolithic command into an extensible subcommand system using a registry pattern. The key benefits are:

1. **Extensibility**: New commands require only a new handler file and registration line
2. **Maintainability**: Each handler is isolated and testable
3. **Backward Compatibility**: Existing "summary" command works unchanged
4. **Clean Architecture**: Clear separation between CLI, handlers, and report logic

The implementation is incremental and low-risk, with comprehensive testing at each step.
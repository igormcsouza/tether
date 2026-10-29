# Shop CLI Refactoring Plan (Phase 1: Documentation)

## Objective
Refactor `shop/cli.py` from a monolithic command into a subcommand registry for future extensibility. This phase is documentation/analysis only; Phase 2 will implement the subcommand infrastructure.

## Current State
- Single monolithic `main()` function with hardcoded "summary" check
- Only supports: `python -m shop.cli summary ORDERS.json`
- Depends on `shop.report.summary` and `shop.storage.load_orders`
- Other report functions exist (`monthly`) but aren't exposed via CLI

---

## 1. Command Dependency Analysis

### Current Flow
```
main()
  ↓
if sys.argv[1] == "summary"
  ↓
    shop.report.summary(shop.storage.load_orders())
```

### Key Dependencies
- **`summary ORDERS.json`**: Depends on `shop.report.summary()` and `shop.storage.load_orders()`
- **`monthly`**: Already defined in `shop.report.monthly()` but not CLI-accessible
- **Other modules**: `cart.py`, `inventory.py`, `pricing.py`, `storage.py` exist but are untapped

---

## 2. Subcommand Registry Design

### Approach: Dispatch Table Registry
A central registry maps command names to their implementation functions with metadata:

```python
# shop/cli.py
import sys
from typing import Callable, Dict, List, Optional, Any

# Command registry (Phase 2 implementation)
_COMMAND_REGISTRY: Dict[str, CommandSpec] = {
    "summary": CommandSpec(
        func=summary_handler,
        args={"filename": {"type": str, "required": True, "help": "Orders file path"}},
        description="Generate summary report",
        short="-s",
        long="--summary",
    ),
    "monthly": CommandSpec(
        func=monthly_handler,
        args={"filename": {"type": str, "required": True, "help": "Orders file path"}},
        description="Generate monthly revenue report",
    ),
}

def main(args: Optional[List[str]] = None) -> int:
    sys_argv = sys.argv[1:] if args is None else args
    
    if not sys_argv or sys_argv[0] not in _COMMAND_REGISTRY:
        print("Usage: python -m shop.cli <command> [options]", file=sys.stderr)
        print("\nAvailable commands:")
        for cmd, spec in _COMMAND_REGISTRY.items():
            print(f"  {spec.short or cmd}: {spec.description}")
        return 1
    
    # Resolve command (Phase 2)
    # ...
```

### Why Dispatch Table Over Callable-Based Registry?
- **Explicit metadata**: Allows defining argument specs, help text, and usage patterns upfront
- **Sensible defaults first**: We get immediate value from the existing design
- **Easy to extend**: New subcommands just add entries to the registry
- **Tooling-friendly**: Metadata can be consumed by static analysis or code generation
- **Phase-2 flexible**: Can be swapped for a callable-based registry if desired

---

## 3. Backward Compatibility Strategy

### Preserve Existing Syntax
The goal is **not** to change:
```bash
python -m shop.cli summary ORDERS.json
```

### Implementation
- Maintain `"summary"` as a first-class registered subcommand
- Implement `summary_handler()` to mirror current behavior exactly
- Phase 2 must ensure zero behavior change for existing users

### Breaking Changes to Avoid
- Do not rename `summary` → `report summary`
- Do not change positional argument order
- Do not change output format

---

## 4. Future Command Candidates

Based on untapped modules:

| Module | Suggested Subcommand | Rationale |
|--------|----------------------|-----------|
| `shop/cart.py` | `cart` / `cart list` | Manage shopping carts, view cart contents, calculate totals |
| `shop/inventory.py` | `inventory` / `inventory check` | Inventory management, stock levels, reorder alerts |
| `shop/pricing.py` | `pricing` / `pricing view` | View pricing rules, calculate discounts |
| `shop/storage.py` | `storage` / `storage status` | Storage health, file metrics, backup status |
| `shop/report.py` | `report monthly`, `report weekly` | Additional reporting functions |

---

## 5. Technical Risks

### Risk 1: Command Discovery Inconsistency
- **Issue**: Mixing `-s` short options across commands creates confusion
- **Mitigation**: Standardize CLI argument patterns in the registry metadata
- **Severity**: Medium

### Risk 2: Ordering/Gating Logic
- **Issue**: If commands need sequential execution or state dependencies
- **Mitigation**: Document sequencing requirements in command spec; implement pipeline mode later
- **Severity**: Low (Phase 2)

### Risk 3: Testing Fragmentation
- **Issue**: Unit tests for each subcommand multiply
- **Mitigation**: Central registry with shared test harness; integration tests exercise full CLI path
- **Severity**: Low

### Risk 4: Naming/Verb Noun Drift
- **Issue**: Inconsistent command patterns (noun vs verb)
- **Mitigation**: Define style guide in registry docstring; start with uniform "noun" commands
- **Severity**: Medium

---

## 6. Implementation Sequencing (Phase 2)

### Step 1: Registry Infrastructure (Sprint 1)
- Define `CommandSpec` dataclass with arg metadata
- Create dispatch table in `cli.py`
- Implement `main()` to route to registry
- Backward compat: `summary ORDERS.json` works identically

### Step 2: First Subcommand (`summary`) (Sprint 1)
- Write `summary_handler()` function
- Add to registry with full metadata
- Test: identical output to current behavior

### Step 3: Second Subcommand (`monthly`) (Sprint 1-2)
- Write `monthly_handler()` function
- Add to registry
- Test: ensure data integrity

### Step 4: Additional Commands (Sprint 2+)
- `cart list`, `inventory check`, `pricing view`
- Each gets its own function + registry entry
- Test incrementally

### Step 5: Argument Parsers & Help Text (Sprint 2)
- Auto-generate help from `CommandSpec` metadata
- Support short/long options
- Test: `python -m shop.cli --help`

---

## 7. Deliverables (Phase 1)

1. **This plan document**: Numbered list with rationale
2. **Technical risk assessment**: Documented above
3. **Command dependency mapping**: Current dependencies identified
4. **Phase 2 sequencing**: Sprint-by-sprint breakdown

## Next Move
- **Phase 2**: Implement the subcommand registry infrastructure based on this plan
- **Testing**: E2E tests on `summary ORDERS.json` to ensure backward compat

---

*Note: This plan focuses on Phase 1 (documentation and analysis). Phase 2 implementation is described for sequencing purposes but no code changes exist yet.*

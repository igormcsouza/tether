# Review Findings

## Critical Security Issues
- `export(subprocess.call(...))`: Shell injection via unsanitized `path` and `partner` string concatenation into `shell=True` command
- `retry(fn)``: Catches all exceptions including `KeyboardInterrupt` and `SystemExit`, blocking shutdown
- `retry(fn)``: Returns `None` on failure without indicating whether original call failed or retry exhausted

## Logic/Reliability Issues
- `export(export(...))`: File deleted after SCP without verifying transfer succeeded
- `retry(fn)`: Catches all exceptions broadly, hiding specific failure modes from caller
- `cache(cached_price)`: No expiration mechanism; cache can store stale data forever
- `sched(nightly)`: No error handling around `retry()` call; failures silently swallowed

## Resource Hazards
- `cache(cached_price)`: Module-level mutable state not thread-safe
- `cache(cached_price)`: No cache size or TTL limits; unbounded memory growth possible
- `sched(nightly)`: Uses synchronous blocking calls in a function that may run frequently

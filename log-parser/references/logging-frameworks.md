# Logging Framework Detection Reference

This document describes how to identify which logging framework a project uses by scanning for specific import patterns, configuration calls, and output formats.

---

## Python Standard Logging

The built-in `logging` module is the most common logging solution in Python.

### Import Patterns

```python
import logging
from logging import getLogger, basicConfig
from logging import FileHandler, RotatingFileHandler, TimedRotatingFileHandler
from logging import StreamHandler, Formatter
```

### Configuration Patterns

```python
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[FileHandler("app.log"), StreamHandler()]
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = RotatingFileHandler("app.log", maxBytes=10485760, backupCount=5)
handler = TimedRotatingFileHandler("app.log", when="midnight", interval=1)
```

### Detection

- Scan `.py` files for `import logging` or `from logging import`
- Look for `logging.getLogger()`, `logging.basicConfig()`
- Check for `FileHandler`, `RotatingFileHandler`, `TimedRotatingFileHandler` instantiations
- Standard logging produces plaintext output with format strings like `%(asctime)s`

---

## Loguru

Loguru is a popular third-party logging library with a simpler API.

### Import Patterns

```python
from loguru import logger
```

### Configuration Patterns

```python
logger.add("app.log", rotation="10 MB", retention="7 days", level="INFO")
logger.add(sys.stderr, format="<red>{time}</red> {message}")
logger.remove()  # Remove default handler
logger.remove(handler_id)
```

### Detection

- Scan for `from loguru import` statements
- Look for `logger.add()` calls with rotation/retention parameters
- Loguru output typically includes ANSI color codes and timestamps by default
- Exception handling with `logger.exception()` is common

---

## Structlog

Structlog produces structured log output, often in JSON format.

### Import Patterns

```python
import structlog
from structlog import get_logger, configure, bind, unbind, wrap_logger
```

### Configuration Patterns

```python
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)
logger = structlog.get_logger()
logger.info("event", key="value", count=42)
```

### Detection

- Scan for `import structlog` or `from structlog import`
- Look for `structlog.configure()` or `structlog.get_logger()`
- Structlog output is often JSON or has key=value pairs
- Bindings like `logger.bind(user_id=123)` are distinctive

---

## JSON Logging

Projects that log JSON directly (without structlog) often use `pythonjsonlogger` or similar.

### Import Patterns

```python
import json
from pythonjsonlogger import jsonlogger
from pythonjsonlogger import json as json_log
```

### Configuration Patterns

```python
handler = logging.StreamHandler()
formatter = pythonjsonlogger.jsonlogger.JsonFormatter(
    fmt="%(asctime)s %(name)s %(levelname)s %(message)s"
)
handler.setFormatter(formatter)
logger.addHandler(handler)
```

### Detection

- Look for `from pythonjsonlogger import json` or `pythonjsonlogger.jsonlogger`
- Each log line is a valid JSON object when parsed
- Expected JSON keys: `timestamp`, `level`, `message`, `name`, `pathname`, `lineno`
- Log files contain one JSON object per line (JSON Lines format)

---

## Kotlin Logging (Autogenesis/TPipe)

Kotlin projects typically use a custom `Logger` interface with `LogCategory` enum.

### Import Patterns

```kotlin
import com.ttt.Logger
import com.ttt.LogCategory
import com.ttt.LogPriority
import com.ttt.LogWriter
```

### Configuration Patterns

```kotlin
Logger.info(LogCategory.NETWORK, "message")
Logger.debug(LogCategory.GENERAL, "message")
Logger.warn(LogCategory.DATABASE, "message")
Logger.error(LogCategory.AUTH, "message")
```

### Detection

- Scan `.kt` files for `Logger.info|debug|warn|error`
- Look for `LogCategory` enum values: SYSTEM, NETWORK, DATABASE, UI, AUTH, LLM, GENERAL
- Log format: `{timestamp} [LEVEL] [CATEGORY]: {message}`
- Log directory: typically `~/.autogenesis/logs/` or `~/.TPipe-Debug/traces/`

---

## Summary Table

| Framework | Import Pattern | Config Pattern | Output Format |
|-----------|---------------|---------------|---------------|
| Standard Logging | `import logging` | `logging.basicConfig()`, `getLogger()` | Plaintext with format placeholders |
| Loguru | `from loguru import logger` | `logger.add()`, `logger.remove()` | Plaintext with ANSI colors |
| Structlog | `import structlog` | `structlog.configure()`, `get_logger()` | JSON or key=value pairs |
| JSON Logging | `from pythonjsonlogger import json` | `JsonFormatter()` | JSON Lines (one object per line) |
| Kotlin Logger | `import com.ttt.Logger` | `Logger.info(LogCategory, msg)` | `{ts} [LEVEL] [CATEGORY]: {msg}` |

---

## Detection Strategy

1. Scan all source files in the project for import statements
2. Match against the import patterns in the table above
3. If multiple frameworks found, check for configuration patterns to determine primary
4. For log files, examine output format (plaintext vs JSON vs ANSI codes)
5. Report the framework(s) detected with confidence level
6. Examine actual log file format to confirm detection
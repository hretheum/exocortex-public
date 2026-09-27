# Exocortex Plugins

Drop a plugin package here for dev-time loading without `pip install`.

## Structure

```
plugins/
  my-plugin/
    __init__.py      ← must expose setup(registry) function
    perspectives.py
    ...
```

## `setup()` contract

```python
from exocortex.core.registry import Registry

def setup(registry: Registry) -> None:
    registry.register_perspective(MyPerspective())
    registry.register_mcp_tool(MyTool())
    # ... register other extension points
```

## Production deployment

For production, declare the entry point in your plugin's `pyproject.toml`:

```toml
[project.entry-points."exocortex.plugins"]
my-plugin = "my_plugin:setup"
```

Then `pip install -e .` in your plugin directory. `Registry.discover()` will
pick it up automatically via `importlib.metadata.entry_points`.

## Five extension points

| Point | Base class | Key | Example |
|---|---|---|---|
| `perspectives` | `PerspectiveType` | `.name` | `client`, `frp` |
| `mcp_tools` | `McpTool` | `.name` | `search_thoughts` |
| `compile_domains` | `DomainCompiler` | `.name` | `work`, `3d` |
| `capture_processors` | `Processor` | `.source_type` | `notion-task-sync` |
| `live_sections` | `SectionGenerator` | `.name` | `open_action_items` |

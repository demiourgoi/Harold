# harold-mcp

Harold MCP tools:

- **Github repository**: <https://github.com/demiourgoi/harold/>
- **Documentation** <https://demiourgoi.github.io>

## Getting started with your project

### Development Environment setup

Then, install the environment with

```bash
make install

# code validations
make check test
```

This will also generate your `uv.lock` file

### Running the server

For development, after `make install` the MCP server runs over stdio with:

```bash
make run
# or directly:
# uv run harold-mcp
```

Then setup the `harold-mcp` command defined on `pyproject.toml` as an MCP server for your IDE, using the command full path. 
For example, for Zed add the following to `~/.config/zed/settings.json`:

```json
  "context_servers": {
    "harold": {
      "enabled": true,
      "remote": false,
      "command": "/home/juanrh/git/demiourgoi/Harold/harold-mcp/.venv/bin/harold-mcp",
      "args": []
    }
  },
  ...
```

and for opencode add the following to `~/.config/opencode/opencode.jsonc`:


```json
  "mcp" : {
    "harold": {
      "type": "local",
      "command": ["/home/juanrh/git/demiourgoi/Harold/harold-mcp/.venv/bin/harold-mcp"],
      "enabled": true
    }
  }
```

For production, harold-mcp will be distributed as a Python package and run with `uvx`. 

## Releasing a new version

- Create an API Token on [PyPI](https://pypi.org/).
- Add the API Token to your projects secrets with the name `PYPI_TOKEN` by visiting [this page](https://github.com/demiourgoi/harold/settings/secrets/actions/new).
- Create a [new release](https://github.com/demiourgoi/harold/releases/new) on Github.
- Create a new tag in the form `*.*.*`.


## References

- Maude
  - [Maude manual](https://maude.lcc.uma.es/maude-manual/)
  - [Bindings docs](https://fadoss.github.io/maude-bindings/)
- [FastMCP](https://gofastmcp.com)
- [OpenCode Python SDK](https://github.com/anomalyco/opencode-sdk-python)
  - [API docs](https://github.com/anomalyco/opencode-sdk-python/blob/main/api.md)

---

Repository initiated with [osprey-oss/cookiecutter-uv](https://github.com/osprey-oss/cookiecutter-uv).

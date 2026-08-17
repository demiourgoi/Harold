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

## Releasing a new version

- Create an API Token on [PyPI](https://pypi.org/).
- Add the API Token to your projects secrets with the name `PYPI_TOKEN` by visiting [this page](https://github.com/demiourgoi/harold/settings/secrets/actions/new).
- Create a [new release](https://github.com/demiourgoi/harold/releases/new) on Github.
- Create a new tag in the form `*.*.*`.

---

Repository initiated with [osprey-oss/cookiecutter-uv](https://github.com/osprey-oss/cookiecutter-uv).

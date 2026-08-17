# harold-mcp

[![Release](https://img.shields.io/github/v/release/demiourgoi/harold)](https://img.shields.io/github/v/release/demiourgoi/harold)
[![Build status](https://img.shields.io/github/actions/workflow/status/demiourgoi/harold/main.yml?branch=main)](https://github.com/demiourgoi/harold/actions/workflows/main.yml?query=branch%3Amain)
[![License](https://img.shields.io/github/license/demiourgoi/harold)](https://img.shields.io/github/license/demiourgoi/harold)

Harold MCP tools:

- **Github repository**: <https://github.com/demiourgoi/harold/>
- **Documentation** <https://demiourgoi.github.io>

## Getting started with your project

### Development Environment setup

Then, install the environment and the pre-commit hooks with

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

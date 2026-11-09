# Makefile for the Agent Skills in this directory.
#
# Every subdirectory containing a SKILL.md is an Agent Skill
# (https://agentskills.io/specification.md). `make validate` checks every
# skill's frontmatter against the official `skills-ref` validator.

# Sandbox-friendly uv locations; harmless elsewhere. Override on the command
# line or in the environment.
UV_CACHE_DIR ?= /tmp/uv-cache
UV_TOOL_DIR ?= /tmp/uv-tools
UV_TOOL_BIN_DIR ?= /tmp/uv-bin
UVX_ENV := UV_CACHE_DIR=$(UV_CACHE_DIR) UV_TOOL_DIR=$(UV_TOOL_DIR) UV_TOOL_BIN_DIR=$(UV_TOOL_BIN_DIR)

# All skill directories. Override to validate a subset:
#   make validate SKILL_DIRS=maude-manual
SKILL_DIRS := $(patsubst %/SKILL.md,%,$(wildcard */SKILL.md))

.PHONY: validate
validate: $(addprefix validate-,$(SKILL_DIRS)) ## Validate every skill in this directory

# Static pattern rule: the targets are listed explicitly, so declaring them
# phony does not suppress the recipe (make skips only *implicit* rule search
# for .PHONY targets).
ifneq ($(strip $(SKILL_DIRS)),)
.PHONY: $(addprefix validate-,$(SKILL_DIRS))
$(addprefix validate-,$(SKILL_DIRS)): validate-%:
	$(UVX_ENV) uvx --from skills-ref agentskills validate $*
endif

.PHONY: help
help: ## List available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help

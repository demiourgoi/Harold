# harold-mcp

Harold is a set of developer tools to make AI-assisted programming with [Maude](https://en.wikipedia.org/wiki/Maude_system) more effective. 

## Project goals

Harold is an MCP (Model Context Protocol) server with tools for programming with the Maude specification and verification language.

Specifically, we want to develop the following tools:

- Diagnose Maude programs (linters, etc.)
- Run Maude programs
- Expose a vector index of the Maude documentation to enable RAG (Retrieval-Augmented Generation)

The use case for Harold is to use it with AI-assisted programming tools such as opencode or Cline, together with LLM models that are not sufficiently trained in the Maude language.

> **Note:** The project is in its early stages. Only a basic skeleton exists right now; none of the MCP tools described above are implemented yet.

## References

- [FastMCP](https://gofastmcp.com/llms.txt)
- [Maude manual](https://maude.lcc.uma.es/maude-manual/)

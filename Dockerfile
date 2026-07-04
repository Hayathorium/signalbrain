# Glama/MCP check image: start the server, answer introspection.
# Verification status: the sb-mcp handshake is proven via pip and uvx installs
# (clean-venv, live PyPI). The Docker build itself was NOT verified at commit
# time — registry CDN was unreachable — despite the prior commit message's
# claim. Corrected here; Glama's own listing check will exercise this image.
FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir ".[mcp]"
CMD ["sb-mcp"]

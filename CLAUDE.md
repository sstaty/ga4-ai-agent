# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

An AI agent that answers natural language questions about Google Analytics 4 data and can write/execute Python code for advanced analysis. Stack: raw Anthropic SDK, FastAPI, Docker sandbox for code execution. GA4 data is accessed via the GA4 MCP server running locally over stdio.

## Package Manager

This project uses `uv`. Never use `pip` directly.


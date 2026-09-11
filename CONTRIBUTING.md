# Contributing to SynapseFlow

Thank you for your interest in contributing.

## Development Setup

```bash
git clone https://github.com/Prabhat-190/synapse-flow-.git
cd synapse-flow
python -m venv .venv && source .venv/bin/activate
make dev
make test
```

## Code Standards

- Python 3.11+
- Run `make lint` before submitting changes
- Add tests for new behavior in `tests/`
- Keep commits focused and descriptive

## Pull Request Process

1. Fork the repository and create a feature branch
2. Ensure CI passes (`make test && make lint`)
3. Update `CHANGELOG.md` for user-facing changes
4. Open a PR with a clear description and test plan

## Reporting Issues

Include:
- Steps to reproduce
- Expected vs actual behavior
- Environment (Python version, OS, Docker vs local)

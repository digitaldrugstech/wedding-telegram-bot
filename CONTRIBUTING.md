# Contributing to Wedding Telegram Bot

Thank you for your interest in contributing to Wedding Telegram Bot! This document provides guidelines and instructions for contributing to the project.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Workflow](#development-workflow)
- [Coding Standards](#coding-standards)
- [Commit Messages](#commit-messages)
- [Pull Request Process](#pull-request-process)
- [Testing](#testing)
- [Reporting Bugs](#reporting-bugs)
- [Suggesting Features](#suggesting-features)

## Code of Conduct

This project follows a Code of Conduct. Please read [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) before contributing.

## Getting Started

### Prerequisites

- Python 3.11 or higher
- PostgreSQL 15 or higher
- Git
- Docker (optional, for testing)

### Setup Development Environment

1. Fork the repository on GitHub

2. Clone your fork:
```bash
git clone https://github.com/YOUR_USERNAME/wedding-telegram-bot.git
cd wedding-telegram-bot
```

3. Add upstream remote:
```bash
git remote add upstream https://github.com/digitaldrugstech/wedding-telegram-bot.git
```

4. Create a virtual environment:
```bash
python3.11 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

5. Install dependencies:
```bash
pip install -r requirements.txt
```

6. Install pre-commit hooks:
```bash
pre-commit install
```

7. Setup environment variables:
```bash
cp .env.example .env
# Edit .env with your test bot token and database credentials
```

8. Run migrations:
```bash
alembic upgrade head
```

## Development Workflow

1. **Create a feature branch** from `master`:
```bash
git checkout master
git pull upstream master
git checkout -b feature/your-feature-name
```

2. **Make your changes** following the coding standards

3. **Test your changes** (see [Testing](#testing))

4. **Commit your changes** (see [Commit Messages](#commit-messages))

5. **Push to your fork**:
```bash
git push origin feature/your-feature-name
```

6. **Create a Pull Request** on GitHub

## Coding Standards

This project follows strict Python coding standards:

### Code Style

- **Line length**: 120 characters maximum
- **Formatter**: [Black](https://github.com/psf/black) with `--line-length 120`
- **Import sorting**: [isort](https://pycqa.github.io/isort/)
- **Linter**: [flake8](https://flake8.pycqa.org/)

Pre-commit hooks will automatically check your code. To run manually:

```bash
# Format code
black --line-length 120 app/ tests/

# Sort imports
isort app/ tests/

# Check code style
flake8 app/ tests/
```

### Code Conventions

- **Type hints**: Use type hints for all function parameters and return values
- **Docstrings**: Write docstrings for all public functions and classes
- **Async/Await**: Use async/await for all I/O operations
- **Error handling**: Always handle exceptions appropriately
- **Logging**: Use structlog for logging, never use print()
- **Database**: Use context managers (`with get_db()`) for database sessions
- **Constants**: Define constants in `app/constants.py`
- **Datetime**: Always use UTC timezone (`datetime.utcnow()`)

### Architecture

- **Handlers**: Keep handlers thin, delegate business logic to services
- **Models**: Define database models in `app/database/models.py`
- **Services**: Business logic goes in `app/services/`
- **Utils**: Reusable utilities in `app/utils/`
- **Decorators**: Use decorators for common checks (`@require_registered`, `@admin_only`, etc.)

## Commit Messages

Follow the [Conventional Commits](https://www.conventionalcommits.org/) specification:

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

### Types

- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, missing semicolons, etc.)
- `refactor`: Code refactoring
- `test`: Adding or updating tests
- `chore`: Maintenance tasks, dependency updates

### Examples

```
feat(jobs): Add interpol fine mechanics

Implement the ability for interpol officers to fine other players
by replying to their messages with /job command.

Closes #42
```

```
fix(work): Correct salary calculation for level 10

The salary range for level 10 was incorrectly capped at 900 instead of 1000.
```

```
docs(readme): Update installation instructions
```

## Pull Request Process

1. **Update documentation** if you've changed APIs or added features

2. **Add tests** for new functionality

3. **Update CHANGELOG.md** following [Keep a Changelog](https://keepachangelog.com/) format

4. **Ensure all checks pass**:
   - Pre-commit hooks
   - Tests (when implemented)
   - No merge conflicts

5. **Write a clear PR description**:
   - What does this PR do?
   - Why is this change needed?
   - How has it been tested?
   - Screenshots (if UI changes)

6. **Request review** from maintainers

7. **Address review comments** promptly

8. **Squash commits** if requested before merge

## Testing

Currently, the project is in the process of adding comprehensive tests. When writing tests:

- Use `pytest` for testing
- Use `pytest-asyncio` for async tests
- Place tests in `tests/` directory
- Name test files `test_*.py`
- Name test functions `test_*`

Run tests:
```bash
pytest tests/
pytest -v  # Verbose output
pytest --cov=app  # With coverage
```

## Reporting Bugs

Before creating a bug report:

1. **Check existing issues** to avoid duplicates
2. **Test with the latest version** from master branch
3. **Collect information**:
   - Python version
   - Operating system
   - Steps to reproduce
   - Expected behavior
   - Actual behavior
   - Error messages/logs

Create a bug report using the [Bug Report template](.github/ISSUE_TEMPLATE/bug_report.md).

## Suggesting Features

Feature suggestions are welcome! Before suggesting:

1. **Check existing issues** and discussions
2. **Consider the scope**: Does this fit the project's goals?
3. **Think about implementation**: Is it technically feasible?

Create a feature request using the [Feature Request template](.github/ISSUE_TEMPLATE/feature_request.md).

## Questions?

- Open a [Discussion](https://github.com/digitaldrugstech/wedding-telegram-bot/discussions)
- Ask in issues with the `question` label

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

Thank you for contributing!

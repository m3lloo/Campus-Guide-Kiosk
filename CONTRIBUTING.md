# Contributing to Campus Guide Kiosk

Thank you for your interest in contributing to Campus Guide Kiosk! This document provides guidelines and instructions for contributing.

---

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Making Changes](#making-changes)
- [Testing](#testing)
- [Code Style](#code-style)
- [Commit Messages](#commit-messages)
- [Pull Request Process](#pull-request-process)

---

## Code of Conduct

We are committed to providing a welcoming and inspiring community for all. Please read and follow our Code of Conduct:

- Be respectful and inclusive
- No harassment, discrimination, or offensive comments
- Report violations to the maintainers

---

## Getting Started

1. **Fork the repository** on GitHub
2. **Clone your fork** locally
3. **Create a new branch** for your feature: `git checkout -b feature/your-feature-name`
4. **Make your changes**
5. **Push to your fork** and submit a pull request

---

## Development Setup

### Prerequisites

- Python 3.8+
- Git
- Docker (optional, for containerized development)

### Local Setup

```bash
# Clone the repository
git clone https://github.com/yourusername/CampusGuideKiosk.git
cd CampusGuideKiosk

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Setup environment
cp .env.example .env

# Edit .env with your configuration (Firebase keys, API keys, etc.)
nano .env

# Run tests
pytest

# Start development server
python app.py
```

### Docker Development

```bash
# Build development image
docker-compose build

# Start services
docker-compose up

# Access application
# http://localhost:5000

# View logs
docker-compose logs -f web
```

---

## Making Changes

### Creating Feature Branches

Use descriptive branch names:

- `feature/add-multilingual-support`
- `bugfix/fix-rate-limiting`
- `docs/improve-readme`
- `chore/update-dependencies`

### Code Organization

```
CampusGuideKiosk/
├── app.py                      # Main Flask application
├── config.py                   # Configuration management
├── error_handlers.py           # Error handling utilities
├── logging_config.py           # Logging setup
├── index.py                    # Admin data manager
├── tests/                      # Test suite
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_error_handlers.py
│   ├── test_routes.py
│   └── test_*.py
├── routes/                     # API route modules (optional)
├── firebase/                   # Firebase configuration
├── templates/                  # HTML templates
├── static/                     # Frontend assets
└── logs/                       # Application logs
```

### File Modifications

When modifying files:

1. **Respect existing code style**
2. **Add docstrings** to functions and classes
3. **Include comments** for complex logic
4. **Update related documentation**

Example function:

```python
def validate_query(query: str, max_length: int = 500) -> str:
    """
    Validate and sanitize user query.
    
    Args:
        query: User input query
        max_length: Maximum allowed query length
        
    Returns:
        Sanitized query string
        
    Raises:
        ValidationError: If query is invalid
    """
    return sanitize_input(query.strip(), max_length)
```

---

## Testing

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=. --cov-report=html

# Run specific test file
pytest tests/test_error_handlers.py

# Run specific test
pytest tests/test_error_handlers.py::TestInputValidation::test_sanitize_input_valid

# Run with verbose output
pytest -v

# Run with debugging
pytest -vv -s
```

### Writing Tests

Create test files in `tests/` directory following the pattern `test_*.py`:

```python
import pytest
from error_handlers import ValidationError, sanitize_input

class TestSanitization:
    """Test input sanitization."""
    
    def test_sanitize_valid_input(self):
        """Test sanitizing valid input."""
        result = sanitize_input("Where is the library?")
        assert result == "Where is the library?"
    
    def test_sanitize_invalid_input(self):
        """Test sanitizing invalid input."""
        with pytest.raises(ValidationError):
            sanitize_input("'; DROP TABLE;")
```

### Test Coverage

Aim for at least 80% code coverage:

```bash
pytest --cov=. --cov-report=term-missing

# Generate HTML report
pytest --cov=. --cov-report=html
# Open htmlcov/index.html in browser
```

---

## Code Style

### Python Style Guide

Follow [PEP 8](https://www.python.org/dev/peps/pep-0008/):

```bash
# Format code with Black
black app.py config.py error_handlers.py

# Check with flake8
flake8 app.py config.py

# Lint with pylint
pylint app.py config.py
```

### Naming Conventions

- **Functions/variables:** `snake_case`
- **Classes:** `PascalCase`
- **Constants:** `UPPER_SNAKE_CASE`

```python
# Good
def load_faq_store():
    pass

class ValidationError(Exception):
    pass

MAX_QUERY_LENGTH = 500

# Avoid
def LoadFaqStore():
    pass

class validationError(Exception):
    pass

maxQueryLength = 500
```

### Imports

Organize imports:

```python
# Standard library
import os
import sys
from functools import lru_cache

# Third-party
import numpy as np
from flask import Flask

# Local imports
from config import config
from logging_config import logger
```

---

## Commit Messages

Write clear, descriptive commit messages:

### Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Types

- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation
- `style`: Code style changes (formatting, missing semicolons, etc.)
- `refactor`: Code refactoring
- `perf`: Performance improvements
- `test`: Adding or updating tests
- `chore`: Build process, dependencies, etc.

### Examples

```
feat(search): add keyword boosting to semantic search
- Implemented keyword extraction from queries
- Added boost factor to FAQ ranking
- Improves relevance for keyword-heavy queries

fix(logging): handle missing logs directory
- Create logs directory if it doesn't exist
- Fixes FileNotFoundError on first run

docs(api): update endpoint documentation
- Added query parameter descriptions
- Documented error responses

test(validation): add comprehensive input tests
- Added tests for injection attacks
- Added tests for length limits
```

---

## Pull Request Process

### Before Submitting

1. **Update your branch** with latest changes:
   ```bash
   git fetch upstream
   git rebase upstream/main
   ```

2. **Run tests** locally:
   ```bash
   pytest --cov=.
   ```

3. **Format code**:
   ```bash
   black .
   ```

4. **Check linting**:
   ```bash
   pylint *.py
   flake8 .
   ```

### Submitting a Pull Request

1. **Push your branch** to your fork:
   ```bash
   git push origin feature/your-feature-name
   ```

2. **Create Pull Request** on GitHub with:
   - Clear title describing the changes
   - Description of what was changed and why
   - Reference to any related issues (#123)
   - Screenshots for UI changes
   - Test coverage information

3. **PR Template**:
   ```markdown
   ## Description
   Brief description of changes.

   ## Type of Change
   - [ ] Bug fix
   - [ ] New feature
   - [ ] Documentation update
   - [ ] Performance improvement

   ## Related Issues
   Fixes #123

   ## Testing Done
   - [ ] Added unit tests
   - [ ] Added integration tests
   - [ ] Manual testing completed

   ## Checklist
   - [ ] Code follows style guidelines
   - [ ] All tests pass
   - [ ] Documentation updated
   - [ ] No breaking changes
   ```

### Review Process

- Code review by maintainers
- May request changes
- Once approved, maintainers will merge
- Your contribution will be acknowledged!

---

## Documentation

### Adding Documentation

- Update relevant `.md` files
- Add docstrings to code
- Include examples where applicable
- Update API.md for new endpoints

### Documentation Format

```python
def search_faqs(user_query: str) -> list:
    """
    Vectorized semantic search over the FAQ store.
    
    This function encodes the user query and computes cosine similarity
    against pre-loaded FAQ embeddings. Results are boosted based on
    keyword overlap.
    
    Args:
        user_query: The user's search query
        
    Returns:
        List of matching FAQs sorted by relevance score:
        [
            {
                'answer': str,
                'score': float (0.0-1.0),
                'category': str,
                'generated_questions': list
            },
            ...
        ]
        
    Example:
        >>> results = search_faqs("Where is the library?")
        >>> print(results[0]['answer'])
        
    Note:
        Requires EMBEDDING_MATRIX to be loaded.
        Returns empty list if no FAQs are available.
    """
```

---

## Reporting Issues

### Bug Reports

Include:
- Description of the bug
- Steps to reproduce
- Expected behavior
- Actual behavior
- Environment (OS, Python version, etc.)
- Logs or error messages
- Screenshots if applicable

### Feature Requests

Include:
- Clear description of the feature
- Use case/motivation
- Potential implementation approach
- Any related issues or discussions

---

## Questions or Need Help?

- Check existing issues and discussions
- Read documentation in `docs/` and `.md` files
- Look at similar code for examples
- Ask in GitHub Discussions

---

## Recognition

Contributors will be:
- Added to CONTRIBUTORS.md
- Credited in release notes
- Recognized in README

---

## License

By contributing, you agree that your contributions will be licensed under the same license as the project (see LICENSE file).

---

Thank you for contributing! 🎉

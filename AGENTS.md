## Coding Guidelines

### Principles

* API is the source of truth — all business logic lives in the backend
* Strict API/UI separation — backend must not control or depend on UI
* GUI is a client — no business logic in the frontend
* DAL is isolated — database should be easily swappable

### Testing

* Prefer functional tests over excessive unit tests
* Test behavior, not implementation

### Python Style

Write Python like Python.

* Prefer readability over cleverness
* Use duck typing and EAFP
* Prefer composition over inheritance
* Keep functions small and classes focused
* Avoid “god objects”
* Use mixins for shared behavior
* Avoid unnecessary abstraction
* Type hints are optional, not authoritative
* Do not design around mypy
* Use string literals for forward references (no `from __future__ import annotations`)
* Avoid abc module unless enforcement is required
* Fail loudly; don’t hide errors
* Keep code simple and obvious
* Follow PEP 8 when it helps, ignore it when it doesn’t
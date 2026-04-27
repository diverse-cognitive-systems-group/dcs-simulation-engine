## Coding Guidelines

* Don't worry about backwards compatibility.
* This project is not yet released, breaking changes are expected and allowed.
* Avoid shortcuts and solve issues completely.
* Ask for clarification.
* Smaller codebases are better than larger codebases.
* Removing code is better than adding code if we can preserve functionality.
* Prefer adding less code if it doesn't impact clarity or maintainability.
* Do not change orval generated code manually

### Principles

* API is the source of truth — all business logic lives in the backend
* Strict API/UI separation — backend must not control or depend on UI
* GUI is a client — no business logic in the frontend
* DAL is isolated — database should be easily swappable

### Python Style

* Prefer idiomatic Python; avoid porting patterns from Java/C# that don’t fit Python.
* Use python 3.13 feature set and above. 
* Prefer readability over cleverness
* Use duck typing and EAFP
* Prefer composition over inheritance
* Keep functions small and classes focused
* Do not design around mypy
* Use string literals for forward references (no `from __future__ import annotations`)
* Avoid abc module unless enforcement is required
* Fail loudly; don’t hide errors
* Keep code simple and obvious
* Follow PEP 8 when it helps, ignore it when it doesn’t

For internal API/Engine code in this part of the monorepo:

(Use Pydantic only at API boundaries—i.e., for validating data ingress and egress.)

* Avoid “god objects”
* Use mixins for shared behavior
* Avoid unnecessary abstraction
* Type hints are optional, not authoritative


### Testing

* Prefer functional tests over excessive unit tests
* Test behavior, not implementation

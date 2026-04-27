# Pull Request Checklist

## Tests
- [ ] All tests pass (`pytest`)
- [ ] 100% coverage maintained

## Code Quality
- [ ] `ruff` passes
- [ ] `black` passes
- [ ] `mypy` passes

## Documentation
- [ ] README.md updated (if needed)
- [ ] CHANGELOG.md updated (if needed)

## Manual Verification
- [ ] CLI works: `python -m src.main add 1 2`
- [ ] Interactive works: `python -m src.main interactive` → `add` → `1` → `2` → `exit`

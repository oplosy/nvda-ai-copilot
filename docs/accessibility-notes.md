# Accessibility Notes

Notes for keeping the NVDA AI copilot addon usable for actual screen reader users.

## Principles

- speech is the primary output; visual output is a bonus, never required.
- Never block or delay NVDA's responsiveness — background work belongs in the coordinator.
- Keyboard interaction should work with NVDA's own commands; avoid global key capture.

## Checklist for changes

- [ ] Tested with a real NVDA session, not just the simulator.
- [ ] No new unmapped shortcuts.
- [ ] Error paths speak something useful instead of staying silent.

Screen reader trust is expensive to lose; err on the side of doing less.

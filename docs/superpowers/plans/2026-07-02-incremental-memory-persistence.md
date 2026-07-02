# Incremental Memory Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make newly formed NPC memories persist to disk during long-running simulations instead of only at the very end.

**Architecture:** Keep decision-time memory retrieval fully in-memory, and add throttled incremental persistence on the server side. Save full scratch state for all personas at checkpoint time, but only rewrite associative memory files for personas whose memory actually changed.

**Tech Stack:** Python 3, Reverie server, persona memory structures, unittest

---

### Task 1: Add Dirty Tracking

**Files:**
- Modify: `reverie/backend_server/persona/memory_structures/associative_memory.py`

- [ ] Mark associative memory dirty when events, thoughts, chats, or relationship updates mutate memory.
- [ ] Clear the dirty flag after a successful save.
- [ ] Keep freshly loaded memory clean after bootstrap.

### Task 2: Add Incremental Persistence

**Files:**
- Modify: `reverie/backend_server/persona/persona.py`
- Modify: `reverie/backend_server/reverie.py`

- [ ] Extend persona save helpers so incremental checkpoints can skip unchanged associative memory and static spatial memory.
- [ ] Add throttled incremental save logic in `ReverieServer` that updates `meta.json`, saves scratch for all personas, and saves associative memory only for dirty personas.
- [ ] Trigger incremental save from the main step loop without affecting the final full save path.

### Task 3: Add Regression Tests

**Files:**
- Create: `test/test_incremental_memory_persistence.py`

- [ ] Verify associative memory dirty tracking toggles correctly on mutation and save.
- [ ] Verify incremental save writes `meta.json`, saves scratch for all personas, and rewrites associative memory only for dirty personas.

### Task 4: Verify

**Files:**
- Test: `test/test_incremental_memory_persistence.py`

- [ ] Run the focused unittest file.
- [ ] Confirm no obvious regressions in nearby memory tests.

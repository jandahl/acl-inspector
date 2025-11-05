# ACL Inspector at a Glance

Think of ACL Inspector as a sidekick for anyone who has ever stared at a firewall configuration and muttered, *“Where exactly is this object used, and what happens if I touch it?”* The tool ingests Cisco ASA configs today (and has early FortiGate support), parses the objects, groups, NAT and ACL lines, and then gives you fast answers to questions that normally demand lots of grep + brainpower.

## What it helps you do

- **Find an object’s footprint.** Type an IP, network, or object name and instantly see every ACL line that references it, flattened into “src/dst/proto” language you can actually reason about. Duplicates and lookalike objects are flagged so you can spot surprises.
- **Compare a change.** Hand it an “old” and “new” object and it highlights which rules the swap would add or remove. Great for change reviews or “what-if” questions.
- **Search across configs.** If you keep multiple ASA configs in a repo, the “Find host” mode will guess which device “owns” a given IP/object and call out other places it appears.
- **Trace packets.** The packet modes combine NAT + ACL (ASA prototype) to tell you whether a specific flow would be allowed, and why.

Behind the scenes the web UI pre-parses configs, keeps an index in memory (and optionally on disk), and lets you shape the output with toggles for raw vs flattened ACL views, card summaries, or config-style text. The CLI and web share the same parsing pipeline, so logic lives in one place.

---

## Friendly Roadmap

Here’s the near-term plan, phrased the way we’ve been talking about it internally:

### 1. Nail ASA fundamentals
- **NAT understanding.** Teach the parser about before/after auto NAT sections, dynamic vs static, PAT, policy entries—the whole ladder—and write tests so order and precedence don’t regress.
- **Interface context.** Attach ACL entries to their interface/direction so the packet views feel grounded in real traffic paths.

### 2. Level up the packet story
- **Owner guesses for packet inputs.** Reuse the “Find host” scoring so both source and destination inherit their likely contexts automatically.
- **Suggested `packet-tracer` commands.** Once we know the interface and object, surface ready-to-copy commands so an engineer can test on the ASA immediately.
- **Explain the verdict.** Expand the packet tab to show a chronological story: NAT translation, ACL hit, and which rule made the decision.

### 3. Big UI rethink (“V2” concept)
- Replace the current tabbed canvas with a single, large search field on an otherwise calm page.
- Offer fuzzy predictive suggestions where each row shows “object/IP (left) … context/firewall (right)”, biased toward the object’s home device.
- After selection, preload the heavy work in the background and reveal modular “cards” or segmented controls that let the user open the exact paths they care about (inspect, compare, packet, etc.). The goal: the experience should feel curated instead of like piloting a cockpit.

### 4. Broader vendor coverage
- Finish the FortiGate parser so policy + NAT queries feel as complete as ASA.
- Keep the intermediate representation (IR) stable and shared so other vendors slot in without rewriting the UI.

### 5. Quality of life
- Keep the documentation and inline comments close to the code so a new engineer can follow the chain from CLI → parser → UI without spelunking.
- Grow the test harness around parsing and the new packet features; every regression should be caught in one place rather than surfacing in production.

---

## How to talk about it

When you describe ACL Inspector to a teammate, a few punchy lines help:

1. “It’s the fastest way we have to answer ‘Where is this used?’ for firewall objects.”
2. “You can try out a change before you touch the config—swap objects in the tool and see the ACL delta immediately.”
3. “It understands NAT + ACL, so you get an opinionated packet-trace without hopping onto the firewall.”

And if they’re more visual: “Open the web UI, type the object name, and it hands you a highlighted card with the object definition, group memberships, and matching ACL lines. You can copy the whole report to your ticket in one go.”

---

## Want to help?

If you’re contributing, the two guiding principles are:

1. **Modularity first.** Keep parsing, state, UI rendering, and background tasks in their own modules so future vendors or UI experiments aren’t blocked by monolithic files.
2. **Document while you go.** Complex parser branches, scoring heuristics, or UI behaviours should have a short comment or doc blurb so the next engineer doesn’t need to reverse-engineer intent.

This repo aims to be the connective tissue between firewall configs and the humans touching them. The more predictable and friendly we make it, the fewer surprises during change windows. Feel free to extend this doc with anything that helps your coworkers on-board faster.


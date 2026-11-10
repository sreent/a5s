# Phase 4: resumable long-running tasks

**Status:** Planned, for implementation in small, separately reviewed steps · **Under:** [Architecture](architecture.md)

a5s already keeps work in records rather than in a process that must stay alive. Long-running tasks extend that rule: a task is a durable record, and each piece of work runs for a bounded time on a fresh worker when needed. There is no permanent LangGraph thread and no hidden state in a worker.

## Done means

A person can start a task that needs more than one run, watch its state and partial results, stop it, and resume it after a failure without repeating effects. The task has an owner, an instance, an audience, a total budget, a deadline, and evidence in the ledger. If it blocks, a person decides what happens next. No task can widen its own permissions, budget, audience, or deadline.

## Build in this order

1. **The task record.** A durable id, owner, instance, audience, task text, status, current step, partial results, total token/duration budget, deadline, and optional parent. States are queued, running, waiting, blocked, done, cancelled and failed. The core alone writes its state through its own interfaces.
2. **Bounded runs and checkpoints.** Each run opens for the task's current step. Code records progress and partial results at tool/action boundaries, never only in the model's context. A new run reads the task record, not an old worker's memory.
3. **Leases and heartbeats.** An active worker renews the task's lease while it works. A stalled lease expires, but one with a live heartbeat does not. A lease is not a budget: both have limits.
4. **Resume and cancellation.** A fresh worker resumes after failure or expiry, with no repeated idempotent effect. Cancellation takes effect at the next core call and stops future runs. A user can see what was already done.
5. **Budgets and blocked work.** The core counts all runs against the task's total budget and deadline. When blocked, the task waits with a reason and its owner or another authorized person decides whether and how to resume it.
6. **Parent and child tasks.** A parent may create only children allowed by its release, for the same or a narrower audience, with the same provenance marks, shared budget and a bounded depth/count. The ledger links each child to its parent. This is not the unrestricted Deep Agents `task` tool.
7. **People's task scheduling.** Where a person asks for a recurring task, it uses the same durable record, an explicit proposal and confirmation, and the existing scheduler. It changes or cancels only with that person's request. This is an extension of the existing reminder/schedule machinery, not another scheduler.

## Tests

- A task survives a worker, scheduler and core restart and resumes without repeating an effect.
- A worker that stops heartbeating loses its lease; one that keeps working does not.
- Cancellation, budget exhaustion and deadlines stop future work and tell the owner what was done.
- A child cannot exceed its parent's audience, permissions, marks, budget, depth or count.
- A user-created schedule needs confirmation, can be changed or cancelled, and acts only for its owner.
- Partial results and every state change are in the ledger, with text kept by hash under the existing data-protection rules.
- A soak test runs tasks through restarts and finds no duplicate effects, lost tasks or growing leases.

## What this does not change

No permanent agent process, unrestricted sub-agent tool, hidden worker state, self-widening permissions, or autonomous approval of blocked work. The existing service-desk and other scenario PRs stay independent of this phase until they need long-running tasks.

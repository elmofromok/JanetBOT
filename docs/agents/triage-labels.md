# Triage Labels

The skills speak in terms of five canonical triage roles. This file maps those roles to the actual label strings used in this repo's issue tracker.

| Label in mattpocock/skills | Label in our tracker | Meaning                                  |
| -------------------------- | -------------------- | ---------------------------------------- |
| `needs-triage`             | `needs-triage`       | Maintainer needs to evaluate this issue  |
| `needs-info`               | `needs-info`         | Waiting on reporter for more information |
| `ready-for-agent`          | `ready-for-agent`    | Fully specified, ready for an AFK agent  |
| `ready-for-human`          | `ready-for-human`    | Requires human implementation            |
| `wontfix`                  | `wontfix`            | Will not be actioned                     |
| _(none)_                   | `deferred`           | Decided and parked: real, out of v1 scope, coming back later |

When a skill mentions a role (e.g. "apply the AFK-ready triage label"), use the corresponding label string from this table.

Edit the right-hand column to match whatever vocabulary you actually use.

## Local additions

`deferred` has no counterpart in the canonical five roles. It was added because
work that has been evaluated and parked has no honest state otherwise:
`wontfix` means will not be actioned and files enhancements to `.out-of-scope/`,
which is for *rejected* requests; `ready-for-*` claims a readiness that does not
exist; and `needs-triage` asserts an evaluation that has already happened.

A `deferred` issue stays open as roadmap. Treat it as fully triaged: do not
surface it in the untriaged or `needs-triage` buckets during `/triage`.

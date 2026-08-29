# A channel holds one Exchange, and a new Summon takes it over

Janet answers the Resident who summoned her, not everyone in the channel, and
a channel holds exactly one Exchange at a time. If a second Resident summons
her while she is Present with someone else, they take her over: the first
Exchange is dismissed and a new one begins. She does not hold parallel
Exchanges with different Residents in the same channel.

Two alternatives were considered. Answering everyone in the channel while
Present is the simplest state, one record per channel with no owner, and it
matches ADR 0001's line that she reads the channel while Present, but it means
she replies to every message in a busy channel including conversation not
directed at her. Holding an Exchange per Resident per channel keeps everyone
served, and was rejected for what it costs downstream rather than for its own
complexity: it turns the cooldown scope, the dismissal scope and above all
Exchange Recall into two-dimensional questions, because overlapping Exchanges
in one channel must each decide whether they can see the other Resident's
messages.

The accepted cost is that a takeover cuts the first Resident off mid-Exchange
with no announcement. On a single private server, two Residents summoning her
in the same channel inside the two-minute window is rare, and the recovery is
to say her name again. This is deliberately the cheap version: presence
tracking lives in its own seam with tests over pure functions, so moving to
per-Resident Exchanges later is a change to one keyed structure, made after
watching how she actually behaves in a channel rather than before.

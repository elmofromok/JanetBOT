# Residents never command Janet; the Operator does

Janet exposes no commands to Residents. She is summoned by name, answers, and
is dismissed by a goodbye or by an idle timeout. Everything she does happens in
conversation, because nobody in the show types a command at Janet, and every
Resident-facing command we considered turned out to be a mechanic we either
deferred or did not want.

The Operator is a separate surface, and it is two controls rather than two
commands. An admin slash command restricted to the Operator switches Janet off
entirely; the per-channel opt-out is an environment variable. Both are
insurance on ADR 0001: bare-word summoning is the riskiest decision in this
design, and without an off switch that does not depend on the model deciding
anything, the only recourse to Janet misfiring is a redeploy. They differ by
lifetime, which is why only one is a command. The off switch is an emergency
and lives in memory, so a restart brings her back. The opt-out is standing
policy that has to survive a restart, and changing it means a redeploy, which
is acceptable for something set rarely. Nobody in the show types at Janet, but
nobody in the show has to run her either.

Adding a Resident-facing command is a change to what Janet is, not a
convenience. Adding an Operator command is ordinary.

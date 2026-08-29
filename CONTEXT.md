# JanetBOT

A Discord bot for a single private server, playing Janet from The Good Place.
Janet is summoned by name, answers in character, and materialises objects on
request. This file is the glossary for that domain, not a spec.

## The character

**Janet**:
The bot's identity: an anthropomorphised vessel of knowledge, in the manner of
the character from The Good Place. Not a girl, not a robot, not an assistant.
_Avoid_: bot, assistant, AI, chatbot

**Resident**:
A person in the Server. Named for the neighbourhood's residents rather than
Discord's "member", which carries no meaning in this domain.
_Avoid_: member, user, player

**Operator**:
The Resident who runs Janet. The only one who can switch her off or exclude a
channel. A role, not a separate kind of person.
_Avoid_: admin, owner, moderator

**The Server**:
The one Discord guild Janet lives in. There is no multi-guild concept and no
per-guild configuration.
_Avoid_: guild, workspace, instance

## Being summoned

**Summon**:
The act by which a Resident causes Janet to appear. Saying her name, or
mentioning her.
_Avoid_: invoke, trigger, ping, wake

**Present**:
The state Janet is in after a Resident summons her, during which she answers
that Resident in that channel without being summoned again. Held for one
Resident per channel: a Summon by anyone else replaces it.
_Avoid_: active, awake, listening, session

**Dismiss**:
The act, or the elapsing, that ends Janet's presence and returns her to the
void.
_Avoid_: sleep, deactivate, timeout, close

**Exchange**:
The run of messages between Janet and one Resident in one channel, from a
Summon to the Dismiss that ends it. The unit Janet reads when answering.
_Avoid_: session, thread, conversation, context

## What she does

Janet is text only. The terms below name a capability she does not yet have,
kept because the concept is real and will return.

**Materialise** (deferred):
To produce an Object at a Resident's request. Her defining ability in the show,
and deliberately out of scope for this build.
_Avoid_: generate, create, render, make

**Object** (deferred):
The thing a Materialise produces.
_Avoid_: image, asset, attachment, output

## What she knows

Three distinct things, deliberately not called "memory".

**Exchange Recall**:
What Janet knows of the current Exchange. Ends when she is dismissed.
_Avoid_: short-term memory, context

**Server Knowledge**:
What has happened in the Server, which Janet can look up. Canonically she knows
everything that has ever happened.
_Avoid_: history, search, long-term memory

**Resident File**:
The durable facts Janet holds about one Resident, surviving any Exchange.
Called a File after the residents' files in the show. Never plain "File",
which collides with filesystem files.
_Avoid_: profile, user data, memory, record

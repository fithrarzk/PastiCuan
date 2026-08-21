# PastiCuan Research Context

PastiCuan produces point-in-time IDX equity research. This glossary defines the language shared by product, analytics, operations, and delivery.

## Evidence and time

**Evidence bundle**:
The complete point-in-time set of facts and provenance used to produce one research result.
_Avoid_: Data blob, payload

**Source class**:
The authority category of evidence: official, licensed, or fallback.
_Avoid_: Provider quality

**Point-in-time**:
A result restricted to information known by its stated cutoff.
_Avoid_: Historical when causality is intended

**Available at**:
The time information became usable to the system, independent of its reporting period.
_Avoid_: Report date, retrieval date

**As of**:
The cutoff timestamp used to select eligible evidence.
_Avoid_: Today, now, latest

**Completed session**:
A fully finished IDX trading session whose closing evidence is eligible for research.
_Avoid_: Trading day when completion is not established

**Freshness**:
The age of eligible evidence relative to the official session calendar.
_Avoid_: Live, current

## Research lifecycle

**Filing**:
An official issuer disclosure for a reporting period.
_Avoid_: Document, report when the official filing is intended

**Source manifest**:
The reviewed catalog of canonical external sources.
_Avoid_: Filing manifest

**Filing manifest**:
The reviewed catalog of official IDX filing attachments.
_Avoid_: Source manifest

**Accepted artifact**:
A retrieved source document that passed validation and is usable as evidence.
_Avoid_: Successful download

**Quarantined artifact**:
A retrieved source document excluded from calculations because validation failed.
_Avoid_: Bad data, ignored file

**Research release**:
The versioned identity of reviewed calculation formulas and their source paths.
_Avoid_: Deployment, model run

**Candidate snapshot**:
A newly built result awaiting the publication boundary.
_Avoid_: Approved snapshot, production snapshot

**Shadow snapshot**:
A reviewed research result that may be displayed but cannot authorize action.
_Avoid_: Production recommendation

**Primary scan**:
A full-universe scan backed by every required production evidence gate.
_Avoid_: Successful scan

**Degraded scan**:
A scan with disclosed missing or fallback evidence and no action eligibility.
_Avoid_: Partial success

**Unavailable scan**:
A fail-closed result whose required evidence or freshness is insufficient.
_Avoid_: Empty scan, broken scan

## Analytics

**LQ45 universe**:
The effective set of 45 IDX constituents for a stated membership period.
_Avoid_: Watchlist

**Issuer profile**:
The verified identity, sector, accounting model, and currency classification of an issuer.
_Avoid_: Company type

**Business score**:
A long-horizon assessment of business quality, valuation, durability, and resilience evidence.
_Avoid_: Stock score, recommendation

**Quant snapshot**:
A persisted cross-sectional factor result with a model and evidence identity.
_Avoid_: Quant score file

**Technical evidence**:
Price and market-behavior observations used to assess timing and execution geometry.
_Avoid_: Prediction, buy signal

**Price-range evidence**:
A research range derived from technical and valuation evidence; never an order instruction.
_Avoid_: Buy range, target order

**Decision gate**:
A rule that determines whether evidence is sufficient for a research state.
_Avoid_: Recommendation rule

**Signal**:
A timestamped research event that can be evaluated against subsequent sessions.
_Avoid_: Trade, order

**Forward outcome**:
The observed result of a prior signal over a defined number of subsequent sessions.
_Avoid_: Backtest prediction

## Operations

**Refresh attempt**:
One scheduled or manually triggered research rebuild.
_Avoid_: Deployment

**Last good snapshot**:
The most recent verified snapshot retained when a newer refresh attempt fails.
_Avoid_: Fallback calculation

**Stale guard**:
The safety rule that prevents old evidence from being presented as current.
_Avoid_: Expiry bug

**Provider fallback**:
A lower-authority source used only with explicit disclosure.
_Avoid_: Equivalent source

**Provider disagreement**:
A material conflict between source observations requiring resolution or degradation.
_Avoid_: Provider noise

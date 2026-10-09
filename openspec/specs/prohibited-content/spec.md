# prohibited-content Specification

## Purpose

How content that a rule excludes leaves the report: only the excluded part goes, nothing still
refers to it, and the report never mentions the excluded topic. What a channel excludes is its
client rules; this capability owns the generic rule that governs every removal.

## Requirements

### Requirement: The removal rule governs every removal

The removal rule SHALL be a generic quality rule (see **source-selection**) with parts for the
report writer and the blind review, rendered as a block of its own in those two steps' prompts. It
SHALL govern every removal, whichever rule asks for it, a client rule included. A rule that
excludes content SHALL hold even when the research question, the approved plan or a review asks for
that content. The grounded review reads the client rules' writer parts so that it does not ask for
excluded content, and the writer keeps it out if a review asks anyway (see **faithful-relay**,
"The grounded review checks the draft against the sources").

The blind review judges it, because a rule that excludes content is checked by its blind part, so
the blind review is the review that knows what is excluded.

- **Report writer:** when a passage must go, removes only its excluded part, keeps the rest of the
  passage, and removes every reference to the excluded part, such as "the table above". Never
  mentions excluded content: does not say that the report does not cover it, does not present it as
  evidence that the sources lack, and does not refer to it later, such as "the requested
  share prices". When the question or the plan asks for excluded content, leaves that part out and
  says nothing about it. A figure or a finding that the sources do not give is not excluded
  content, unless a rule excludes its topic: the writer says that the sources do not give it, as "No
  calculations" and "Gaps in the
  evidence" ask.
- **Blind review:** excluded content in the draft is a violation of the rule that excludes it, even
  when the question or the plan asks for it. When it reports a passage that must go, it also
  reports, in the same list, every passage that refers to it, so that one revision fixes all of
  them, because the last version is delivered unreviewed. Any mention of excluded content is a
  violation: a sentence that says the report does not cover it, excluded content presented as
  evidence that the sources lack, and a later reference to it. A part of the question that asks for
  excluded content, left out without comment, is correct, and so is a statement that the sources do
  not give a figure or a finding whose topic no rule excludes.

The writer's rule that the report does not explain a declined part of a request (see
**source-selection**, "The rules and the existing prompt text do not contradict each other") SHALL
stay as it is, with no exception for excluded content. The writer's list of rules that outrank the
request SHALL name the rules that exclude content, so that the report request's "covering every
item of the plans" never reads as an order to cover an excluded topic.

#### Scenario: The outrank list names the exclusion rules

- **WHEN** the writer's system prompt is rendered
- **THEN** its list of rules that outrank the request SHALL include the rules that exclude content

#### Scenario: A reference to a removed table is flagged with it

- **WHEN** the blind review reports a table for removal and a later paragraph says "as the table
  above shows"
- **THEN** the same review SHALL report that paragraph too

#### Scenario: A question that asks for excluded content

- **WHEN** the question and the approved plan ask for share-price forecasts, and a client rule
  excludes share-price forecasts
- **THEN** the blind review SHALL report a draft that gives or discusses them, and the report SHALL
  leave that part out without saying that it does not cover it

#### Scenario: A "does not cover" sentence is a violation

- **WHEN** a draft says "This report does not cover share-price forecasts."
- **THEN** the blind review SHALL report the sentence as a violation

#### Scenario: A review asks for excluded content

- **WHEN** the grounded review asks for a value to be added and a client rule excludes it
- **THEN** the writer SHALL leave the value out of the revision

#### Scenario: A figure no source gives is still declared

- **WHEN** the question asks for a growth rate that only a calculation would give, and the draft
  says that the sources do not give it
- **THEN** the blind review SHALL NOT report the sentence under the removal rule

#### Scenario: An excluded topic presented as missing evidence

- **WHEN** a draft says "the sources do not give the requested share-price forecasts"
- **THEN** the blind review SHALL report the sentence as a violation

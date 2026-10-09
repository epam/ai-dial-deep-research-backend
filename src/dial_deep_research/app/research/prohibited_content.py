"""The removal rule: how content that a rule excludes leaves the report.

What a channel excludes is its client rules. This rule governs every removal, whichever rule asks
for it: only the excluded part goes, nothing still refers to it, and the report never mentions the
excluded content, not even to say that it does not cover it. The last version of the report is
delivered unreviewed, so the blind review reports a passage and every reference to it in one review,
for one revision to fix. The blind review judges the rule because a rule that excludes content is
checked by its blind part, so the blind review is the one that knows what is excluded.
"""

from __future__ import annotations

from dial_deep_research.app_properties import QualityRule

REMOVAL_RULES: tuple[QualityRule, ...] = (
    QualityRule(
        name="Removal",
        report_writer="""\
A rule that excludes content applies even when the research question, the plan or a review asks for
that content.
When a passage must go, remove only its excluded part. Keep the rest of the passage. Also remove
every reference to the excluded part, such as "the table above".
Never mention excluded content in the report:
- do not say that the report does not cover it;
- do not present it as evidence that the sources lack;
- do not refer to it later, such as "the requested share prices".
If the question or the plan asks for excluded content, leave that part out. Say nothing about
it.
A figure or a finding that the sources do not give is not excluded content, unless a rule excludes
its topic. Say that the sources do not give it, as the rules on calculations and on missing evidence
ask.""",
        report_review_blind="""\
A rule that excludes content applies even when the research question or the plan asks for that
content. Such content in the draft is a violation of that rule.
When you report a passage that must go, also report every passage that refers to it, such as "the
table above". Report them in the same list, so that one revision fixes all of them.
Any mention of excluded content is a violation. This includes:
- a sentence that says the report does not cover it;
- excluded content presented as evidence that the sources lack;
- a later reference to it, such as "the requested share prices".
If the question asks for excluded content and the draft leaves it out without comment, that is
correct. A statement that the sources do not give a figure or a finding is correct too, unless a
rule excludes its topic.""",
    ),
)

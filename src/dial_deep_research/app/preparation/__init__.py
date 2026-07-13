"""Preparation agent that fronts each chat completion turn.

A single-context LangChain tool-calling agent clarifies the query, aligns with the
user on a research plan, and gates the (deferred) research launch behind a typed
`PrepState` the agent can read but not write — only the tools mutate it. Turns are
stateless: `PrepState` and the transcript ride on DIAL custom state. See the
`clarification-and-plan-alignment` OpenSpec change.
"""

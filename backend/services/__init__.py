"""Service-layer integrations: Lob, Stripe, etc. Single-responsibility
wrappers around external APIs. No DB writes happen here — that's the
caller's job. These modules are unit-testable in isolation and can be
mocked at the call site for tests.
"""

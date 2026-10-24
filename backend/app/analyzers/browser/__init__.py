"""On-device analysis backend (default).

The caller's browser transcribes speech and classifies sounds locally and sends the
results with each chunk; the server fuses them with the rule router. No API keys and no
server-side models, so it runs from a clean clone. Signals are client-asserted: a
hostile client can claim anything, which is why a human confirms every dispatch.
"""

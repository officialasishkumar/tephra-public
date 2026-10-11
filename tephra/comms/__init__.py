"""Crew and passenger messages and the shift handover brief.

Everything here is a DRAFT until a dispatcher decides it, and an approved message goes only
to TEPHRA's own ``outbound`` collection. The model writes text with placeholders; code fills
every fact. There is no stand-in text when the model fails: the caller gets
``AiUnavailable`` (docs/EXTENSIONS.md rule 0).
"""

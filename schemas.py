"""Tool schemas: what the model reads when deciding to call Dossier.

Descriptions are specific about *when* to use each tool, because that sentence
is the whole routing decision.
"""

NAME = {
    "name": "dossier_build",
    "description": (
        "Build or refresh a sourced, dated dossier on an organisation, or on a person in a "
        "professional public capacity. Use before a meeting, a sales call, an interview or a "
        "partnership conversation. Every fact in the brief cites a fetched source with a "
        "publication and retrieval date, and contradictions are kept as contested rather than "
        "resolved. Returns a short card plus the path to the full A4 brief. Ask for a "
        "disambiguator (domain, employer, location) when the name is ambiguous."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Entity name, e.g. 'Kalamari' or 'Sarah Chen'."},
            "kind": {"type": "string", "enum": ["org", "person"], "description": "Defaults to org unless the name looks like a person."},
            "domain": {"type": "string", "description": "The organisation's own domain, when known. Pins the entity and stops name collisions."},
            "github": {"type": "string", "description": "GitHub organisation slug, when known."},
            "disambiguator": {"type": "string", "description": "Employer, role or location that tells two same-name entities apart."},
            "purpose": {
                "type": "string",
                "description": (
                    "Why this dossier exists, in the user's words: 'interview for the platform role "
                    "on Thursday', 'first call with their procurement team'. It is stored and printed "
                    "on the brief, and it steers the questions."
                ),
            },
            "context": {
                "type": "string",
                "enum": ["general", "interview", "sales", "partnership", "diligence", "supplier"],
                "description": (
                    "What the reader is preparing for. Changes the questions and the risk heading: "
                    "an interview gets team and role questions, a sales meeting gets spend, sign-off "
                    "and urgency questions. Infer it from what the user says they are doing."
                ),
            },
        },
        "required": ["name"],
    },
}

SHOW = {
    "name": "dossier_show",
    "description": (
        "Show the stored dossier for an entity that has already been built. Returns the latest "
        "brief card, its generation date, and the path to the full A4 HTML brief. Use when the "
        "user asks what is already known about an entity."
    ),
    "parameters": {
        "type": "object",
        "properties": {"name": {"type": "string", "description": "Entity name or numeric dossier id."}},
        "required": ["name"],
    },
}

DIFF = {
    "name": "dossier_diff",
    "description": (
        "Report what changed in an entity's dossier since the previous snapshot: new claims, "
        "dropped claims, and claims whose confidence or status moved. This is the pre-meeting "
        "question, 'what is different since I last looked?'"
    ),
    "parameters": {
        "type": "object",
        "properties": {"name": {"type": "string", "description": "Entity name or numeric dossier id."}},
        "required": ["name"],
    },
}

REFRESH = {
    "name": "dossier_refresh",
    "description": (
        "Re-fetch the sources for an existing dossier and store a new snapshot, then report the "
        "diff against the previous one. Use before a meeting when the stored brief is stale."
    ),
    "parameters": {
        "type": "object",
        "properties": {"name": {"type": "string", "description": "Entity name or numeric dossier id."}},
        "required": ["name"],
    },
}

WATCH = {
    "name": "dossier_watch",
    "description": (
        "Set how often a stored dossier should be refreshed: off, manual, daily or weekly. Record the "
        "calendar or meeting hint that makes the refresh worth doing (e.g. 'board meeting first "
        "Tuesday'). Use when the user says to keep an eye on an entity, or to stop."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Entity name or numeric dossier id."},
            "cadence": {"type": "string", "enum": ["off", "manual", "daily", "weekly"], "description": "Refresh cadence."},
            "calendar_hint": {"type": "string", "description": "Why and when: the meeting or event this is for."},
        },
        "required": ["name", "cadence"],
    },
}

ALL = (NAME, SHOW, DIFF, REFRESH, WATCH)

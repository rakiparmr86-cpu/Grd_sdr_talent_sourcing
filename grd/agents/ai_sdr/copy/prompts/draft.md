# PLACEHOLDER - Copy agent (workflow step 2.3) is not built yet.
# When it is, this prompt drafts one personalized outreach message using ONLY
# facts from the research profile + tone from copy/voice_corpus (RAG).

Write a {channel} outreach message to {contact_name} ({contact_title}) at
{company_name}.

Rules:
- <= {max_words} words.
- Reference at least one concrete fact from RESEARCH (cite which).
- Match the tone of the VOICE examples. Make no claim not supported by RESEARCH
  or VOICE.
- End with {sender_identity} and, for email, a one-line opt-out.

RESEARCH: {research_json}
MATCHED SIGNALS: {matched_signals}
VOICE EXAMPLES: {voice_snippets}
OFFER: {offer}

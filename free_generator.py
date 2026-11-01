"""
Template-Based Email Generator (compatibility wrapper).

Emails are now generated per candidate by the pipeline:
candidate profile + best of the 5 Template Library examples + analysed JD.
This module keeps the old `generate_template_email` entry point working for
the currently active candidate — no candidate details are hardcoded here.
"""


def generate_template_email(recruiter: dict, signature: str = "", api_key: str = None) -> tuple[str, str]:
    """
    Generate a personalised email for one recruiter/job using the ACTIVE candidate.
    Returns (subject, body).  Raises RuntimeError if no candidate is configured.
    """
    import candidate_store as cs
    from pipeline import generate_for_job, jd_for_record, load_context
    from settings import load_settings

    ctx = load_context(cs.get_active_candidate_id())
    if ctx is None:
        raise RuntimeError("No candidate configured. Open Candidate Setup first.")
    if not ctx.templates:
        raise RuntimeError("No templates configured. Open the Template Library first.")
    settings = load_settings()
    fields = generate_for_job(jd_for_record(recruiter), ctx, api_key or settings.get("openai_api_key", ""),
                              bool(settings.get("use_openai_drafting")))
    return fields.get("generated_subject", ""), fields.get("generated_body", "")

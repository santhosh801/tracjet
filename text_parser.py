"""
Free LinkedIn Post Parser
Extracts recruiter details from raw pasted LinkedIn job posts.
No AI or API keys required.
"""
import re


def clean_recruiter_name(name: str) -> str:
    if not name:
        return ""
    # Strip common LinkedIn prefixes and suffixes
    cleaned = re.sub(r'^(View|Connect|Follow|Message|See More|Hiring|Recruiter)\s+', '', name, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s+(profile|member|online|active|status|button|link|icon)$', '', cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip()
    
    # Check if there are still any bad words suggesting it's not a real name
    bad_terms = ["view", "connect", "follow", "message", "see more", "profile", "member", "status", "hiring", "recruiter", "hr", "talent"]
    cleaned_lower = cleaned.lower()
    if any(term in cleaned_lower for term in bad_terms):
        return ""
        
    # Ensure it's mostly characters
    if not re.match(r'^[A-Za-z\s\.]+$', cleaned):
        return ""
        
    tokens = cleaned.split()
    if not tokens:
        return ""
        
    first_name = tokens[0]
    if len(first_name) <= 1 and len(tokens) > 1:
        first_name = tokens[1]
    if len(first_name) <= 1:
        return ""
        
    return first_name.capitalize()


def clean_job_title(role: str, name: str = "") -> str:
    if not role:
        return "Software Developer"
        
    cleaned = role.strip()
    
    # Remove recruiter name if it got captured in the title
    if name:
        cleaned = re.sub(re.escape(name), '', cleaned, flags=re.IGNORECASE)
        for tok in name.split():
            if len(tok) > 2:
                cleaned = re.sub(r'\b' + re.escape(tok) + r'\b', '', cleaned, flags=re.IGNORECASE)
                
    # Remove junk characters
    cleaned = re.sub(r'[#🚀📢\*\|•\-\–\(\)]', ' ', cleaned)
    cleaned = re.sub(r'^(Hiring|Role|Position|Job Title|Looking for|We\'re Hiring|We are hiring for)\s+', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\b(role|position|opening|job|vacancy)\b', '', cleaned, flags=re.IGNORECASE)
    
    # Strip trailing locations like "in Chennai" or "in Bangalore"
    cleaned = re.sub(r'\s+in\s+[A-Za-z\s]+$', '', cleaned, flags=re.IGNORECASE)
    
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    if len(cleaned) < 3:
        return "Software Developer"
        
    # Standardize titles
    cleaned = re.sub(r'\bdev\b', 'Developer', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\bsde\b', 'Software Development Engineer', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\beng\b', 'Engineer', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\bqa\b', 'QA Engineer', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\bui/ux\b', 'UI/UX Designer', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\bfullstack\b', 'Full Stack Developer', cleaned, flags=re.IGNORECASE)
    
    words = cleaned.split()
    cap_words = []
    for w in words:
        if w.lower() in ("ai", "ml", "qa", "aws", "gcp", "c#", ".net", "sde"):
            cap_words.append(w.upper() if w.lower() != "c#" else "C#")
        else:
            cap_words.append(w.capitalize())
    cleaned = " ".join(cap_words)
    
    if cleaned.startswith("S ") or cleaned.startswith("I ") or cleaned.startswith("A "):
        cleaned = cleaned[2:].strip()
    if cleaned.lower() in ("developer", "engineer", "role", "dev"):
        return "Software Developer"
        
    return cleaned


def parse_linkedin_posts(raw_text: str) -> list[dict]:
    """
    Parse raw LinkedIn feed text (single or bulk paste) and extract job posts.
    Every post is analysed independently by jd_analyzer; jobs without a recruiter
    email are kept (with an empty email) so they stay visible but can never be sent.
    Returns a list of dicts with recruiter details.
    """
    from pipeline import parse_jobs
    results = []
    for a in parse_jobs(raw_text):
        results.append({
            'recruiter_name': a.get('recruiter_name', ''),
            'company': a.get('company', ''),
            'email': a.get('email', ''),
            'job_title': a.get('job_title', ''),
            'location': a.get('location', ''),
            'experience': a.get('experience', ''),
            'skills_required': ', '.join(a.get('required_skills', [])[:12]),
            'jd': a.get('text', ''),
        })
    return results

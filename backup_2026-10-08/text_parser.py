"""
Free LinkedIn Post Parser
Extracts recruiter details from raw pasted LinkedIn job posts.
No AI or API keys required.
"""
import re
import random


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
    Parse raw LinkedIn feed text and extract recruiter job posts.
    Returns a list of dicts with recruiter details.
    """
    # Normalize newlines and split line-by-line
    lines = raw_text.splitlines()
    chunks = []
    current_chunk = []
    
    for line in lines:
        line_stripped = line.strip()
        # If we see a separator/header line, start a new chunk
        if line_stripped == "Feed post" or (line_stripped.lower().startswith("view ") and "profile" in line_stripped.lower()):
            if current_chunk:
                chunks.append("\n".join(current_chunk))
                current_chunk = []
        current_chunk.append(line)
        
    if current_chunk:
        chunks.append("\n".join(current_chunk))
    
    results = []
    seen_emails = set()

    for chunk in chunks:
        if len(chunk.strip()) < 30:
            continue

        emails = re.findall(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', chunk)
        emails = [e for e in emails if not any(skip in e.lower() for skip in 
                  ['acte.in', 'youtube', 'lnkd.in', 'tvktechs', 'lyl.ai', 'example'])]
        
        if not emails:
            continue
            
        is_placeholder = False
        for email in emails:
            if email.lower() in seen_emails:
                continue
            seen_emails.add(email.lower())

            # Extract recruiter name from profile header
            name = ""
            name_match = re.search(r'(?:View\s+)?([A-Z][a-z]+ [A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)', chunk)
            if name_match:
                name = clean_recruiter_name(name_match.group(1))

            # Extract company
            company = ""
            company_patterns = [
                r'(?:@|at)\s+([A-Za-z0-9\s&]+)',
                r'Company:\s*([^\n]+)',
                r'🏢\s*(?:Company:?)?\s*([^\n]+)',
            ]
            for pat in company_patterns:
                m = re.search(pat, chunk)
                if m:
                    company = m.group(1).strip()[:60]
                    break

            # Extract job title/role
            role = ""
            role_patterns = [
                r'(?:Hiring|Role|Position|Job Title)[:\s]*([^\n]{5,80})',
                r'(?:Looking for|We\'re Hiring)[:\s|]*([^\n]{5,80})',
                r'#Hiring[:\s]*([^\n]{5,80})',
            ]
            for pat in role_patterns:
                m = re.search(pat, chunk, re.IGNORECASE)
                if m:
                    role = re.sub(r'[#🚀📢\*\|]', '', m.group(1)).strip()[:80]
                    break
                    
            if not role:
                # Fallback: scan first 6 lines of chunk for job titles
                lines_in_chunk = [line.strip() for line in chunk.split('\n') if line.strip()][:6]
                for line in lines_in_chunk:
                    if any(kw in line.lower() for kw in ("developer", "engineer", "designer", "architect", "analyst", "lead", "sde", "hiring", "role")):
                        cleaned_line = re.sub(r'^(View|Connect|Follow|Message|See More|member|profile|online|active)\b', '', line, flags=re.IGNORECASE)
                        cleaned_line = re.sub(r'@\s*[A-Za-z0-9\s&]+', '', cleaned_line)
                        cleaned_line = cleaned_line.split('|')[0].split('-')[0].split(',')[0].strip()
                        if 5 <= len(cleaned_line) <= 80:
                            role = cleaned_line
                            break
                            
            role = clean_job_title(role, name)

            # Extract location
            location = ""
            loc_match = re.search(r'(?:📍|Location)[:\s]*([^\n]{3,60})', chunk, re.IGNORECASE)
            if loc_match:
                location = re.sub(r'[📍]', '', loc_match.group(1)).strip()[:60]

            # Extract experience
            exp = ""
            exp_match = re.search(r'(?:💼|Experience)[:\s]*([^\n]{3,40})', chunk, re.IGNORECASE)
            if not exp_match:
                exp_match = re.search(r'(\d+[\-–+]\s*\d*\s*(?:years|yrs|Year))', chunk, re.IGNORECASE)
            if exp_match:
                exp = exp_match.group(1).strip()[:40]

            # Extract skills
            skills = []
            skill_keywords = ['Java', 'Python', 'React', 'Angular', 'Node.js', 'Spring Boot',
                            '.NET', 'AWS', 'Azure', 'GCP', 'Docker', 'Kubernetes',
                            'Microservices', 'REST API', 'SQL', 'MongoDB', 'TypeScript',
                            'JavaScript', 'HTML', 'CSS', 'FastAPI', 'Django', 'Flask',
                            'LLM', 'GenAI', 'RAG', 'AI', 'Machine Learning', 'Kafka',
                            'Vue.js', 'PostgreSQL', 'MySQL', 'Oracle', 'Git', 'CI/CD',
                            'Hibernate', 'JPA', 'Spring', 'C#', 'Terraform']
            chunk_lower = chunk.lower()
            for skill in skill_keywords:
                if skill.lower() in chunk_lower:
                    skills.append(skill)

            # Extract JD (truncated chunk)
            jd = chunk[:1500].strip()

            results.append({
                'recruiter_name': name,
                'company': company,
                'email': email,
                'job_title': role,
                'location': location,
                'experience': exp,
                'skills_required': ', '.join(skills[:12]),
                'jd': jd,
            })

    return results

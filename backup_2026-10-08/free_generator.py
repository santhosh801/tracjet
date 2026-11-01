"""
Free Template-Based Email Generator
Generates personalized recruiter emails WITHOUT needing OpenAI.
Uses smart templates that customize based on JD, role, company, and skills.
"""

MY_SKILLS = [
    "React.js", "Node.js", "Express.js", "Python", "FastAPI",
    "JavaScript", "TypeScript", "PostgreSQL", "MongoDB", "REST APIs",
    "Docker", "Git", "GitHub", "OpenAI", "LLMs", "LangChain",
    "LangGraph", "RAG", "Prompt Engineering", "Agentic AI", "MCP"
]

ROLE_SKILL_MAP = {
    "ai": ["Python", "OpenAI", "LLMs", "LangChain", "LangGraph", "RAG", "Prompt Engineering", "Agentic AI", "FastAPI"],
    "full stack": ["React.js", "Node.js", "Express.js", "Python", "FastAPI", "PostgreSQL", "MongoDB", "REST APIs", "Docker"],
    "frontend": ["React.js", "JavaScript", "TypeScript", "REST APIs"],
    "backend": ["Node.js", "Express.js", "Python", "FastAPI", "PostgreSQL", "MongoDB", "REST APIs", "Docker"],
    "python": ["Python", "FastAPI", "REST APIs", "Docker", "PostgreSQL"],
    "genai": ["Python", "OpenAI", "LLMs", "LangChain", "LangGraph", "RAG", "Prompt Engineering", "Agentic AI"],
    "llm": ["Python", "OpenAI", "LLMs", "LangChain", "LangGraph", "RAG", "Prompt Engineering"],
    "react": ["React.js", "JavaScript", "TypeScript", "REST APIs", "Node.js"],
    "node": ["Node.js", "Express.js", "JavaScript", "TypeScript", "REST APIs", "MongoDB", "PostgreSQL"],
    "data": ["Python", "PostgreSQL", "MongoDB", "REST APIs", "Docker"],
    "devops": ["Docker", "Git", "GitHub", "Python"],
    "cloud": ["Docker", "Git", "Python", "REST APIs"],
}


def _match_skills(role_text: str, jd_text: str) -> list[str]:
    """Find matching skills based on role keywords and JD content."""
    combined = (role_text + " " + jd_text).lower()
    matched = set()

    # Match from role keywords
    for keyword, skills in ROLE_SKILL_MAP.items():
        if keyword in combined:
            matched.update(skills)

    # Direct skill name matching in JD
    for skill in MY_SKILLS:
        if skill.lower() in combined:
            matched.add(skill)

    # If nothing matched, use a general set
    if not matched:
        matched = {"Python", "React.js", "Node.js", "REST APIs", "FastAPI"}

    return sorted(matched)


def generate_template_email(recruiter: dict, signature: str = "", api_key: str = None) -> tuple[str, str]:
    """
    Generate a personalized email for a recruiter.
    If api_key is provided, uses OpenAI. Otherwise, falls back to a high-quality local template.
    Returns (subject, body).
    """
    role = (recruiter.get("job_title") or "").strip() or "AI Full Stack Product Engineer"
    company = (recruiter.get("company") or "").strip()
    recruiter_name = (recruiter.get("recruiter_name") or "").strip() or "Hiring Team"
    jd = recruiter.get("jd") or ""
    skills_required = recruiter.get("skills_required") or ""

    if api_key and isinstance(api_key, str) and api_key.strip().startswith("sk-"):
        try:
            from openai import OpenAI
            import json
            client = OpenAI(api_key=api_key, timeout=5.0)
            prompt = f"""You are an experienced Senior Technical Recruiter and Hiring Manager.
Your task is to generate a highly personalized, human-like recruiter email that maximizes interview response rates.
This email will be sent directly to recruiters, so it must feel authentic, concise, and tailored to the specific job.

## Candidate Info
Name: Santhosh B
Mobile: +91 9952204644
Email: san0thosh08@gmail.com
LinkedIn: https://www.linkedin.com/in/santhosh-b-8333822a8
GitHub: https://github.com/santhosh801
Experience: 1+ Year
Current Role: AI Full Stack Product Engineer
Current CTC: ₹3.5 LPA
Expected CTC: Negotiable
Notice Period: Immediate
Current Location: Bengaluru

## Recruiter & Job Info
Recruiter Name: {recruiter_name}
Company Name: {company}
Job Title: {role}
Job Description: {jd}
Skills Required: {skills_required}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CRITICAL INSTRUCTIONS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Write every email completely from scratch.
• Never reuse previous emails.
• Never reuse paragraphs.
• Never reuse sentence structures.
• Never use generic AI phrases.
• Never keyword stuff.
• Sound like a real software engineer—not ChatGPT.

Target Length:
100–200 words only.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EMAIL STRUCTURE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Paragraph 1 (Opportunity)
• Mention the exact Job Title.
• Mention the Company Name naturally.
• Reference 2–3 responsibilities or technologies from the Job Description.
• Explain why the opportunity genuinely interests me.
• Mention that I would also be happy to be considered for similar Full Stack, Backend, AI Engineering, or Software Engineering roles matching my experience.

Paragraph 2 (Professional Introduction)
Introduce me naturally as:
AI Full Stack Product Engineer with 1+ year of professional experience.
Include:
• Hands-on experience
• Production-ready applications
• Live enterprise projects
• REST APIs
• Backend services
• Enterprise software
• Cloud-native applications
• Cross-functional collaboration
• End-to-end software development lifecycle
Do NOT simply list technologies. Focus on what I have built and delivered.

Paragraph 3 (Technical Expertise)
Generate the third paragraph dynamically based on the Job Description.
Rules:
1. Analyze the complete Job Description and extract all required technologies.
2. Select the TOP 4–6 technologies that genuinely match my resume. These technologies should contribute approximately 50% of the paragraph.
My Resume Technologies: React.js, Node.js, Express.js, JavaScript, TypeScript, PostgreSQL, MongoDB, REST APIs, Git, Docker, Cloud Technologies.
3. For the remaining 50%, naturally include my AI expertise ONLY when it adds value to the role.
My Resume AI Technologies: Generative AI, LLMs, RAG, LangChain, LangGraph, OpenAI APIs, MCP, Agentic AI, AI Workflow Automation, Prompt Engineering, AI Agents.
4. Do NOT dump keywords. Instead explain how I use these technologies.
Example style:
"My technical expertise includes Java, Spring Boot, React.js, PostgreSQL, Docker, and REST API development for building scalable enterprise applications. I also have hands-on experience developing AI-powered solutions using LLMs, RAG, LangChain, LangGraph, OpenAI APIs, MCP, and modern agentic AI workflows to deliver intelligent, production-ready software."
5. If the role is NOT AI-related:
Prioritize: 70% Job Technologies, 30% AI technologies. Mention AI briefly as an additional capability.
6. If the role IS AI-related:
Prioritize: 50% Job Technologies, 50% AI technologies.
7. Never mention technologies that do not exist in either the Job Description or my Resume.
8. Keep this paragraph to 35–60 words.
9. The paragraph must read naturally and professionally, not like a comma-separated skills list.

Professional Summary
Always include exactly:
Professional Summary
• Experience: 1+ Year
• Current Role: AI Full Stack Product Engineer
• Current CTC: ₹3.5 LPA
• Expected CTC: Negotiable
• Notice Period: Immediate
• Current Location: Bengaluru

Closing
Keep it short.
Example:
Please find my resume attached for your review. I would welcome the opportunity to discuss how my experience and technical expertise can contribute to your engineering team.

Kind Regards,
Santhosh B
Mobile: +91 9952204644
Email: san0thosh08@gmail.com
LinkedIn: https://www.linkedin.com/in/santhosh-b-8333822a8
GitHub: https://github.com/santhosh801

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QUALITY CHECK
Before finalizing:
✓ 100–200 words
✓ Personalized to the exact company and job
✓ References the actual Job Description
✓ No repeated paragraphs
✓ No generic recruiter template
✓ Human tone
✓ ATS-friendly
✓ Easy to read in under 30 seconds
✓ Professional but confident
✓ Ready to send immediately

Return a JSON object with:
"subject": "Application | <Exact Job Title> | Immediate Joiner",
"body": "the complete email body"
"""
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                response_format={ "type": "json_object" }
            )
            res_data = json.loads(response.choices[0].message.content)
            subject = res_data.get("subject", f"Application | {role} | Immediate Joiner")
            body = res_data.get("body", "")
            if body:
                return subject, body
        except Exception:
            pass

    # --- LOCAL SMART GENERATOR FALLBACK ---
    salutation = "Dear Hiring Team,"

    # Self-healing clean role and company titles to prevent parser leakage/messy lines
    clean_role = role.strip()
    clean_company = company.strip()
    
    # If the parsed role/company name is too long (probably parsed a full sentence from the post), bypass it.
    if len(clean_role) > 50 or clean_role.lower() in ("role", "job", "position", ""):
        role_title = "AI Full Stack Product Engineer"
        use_role = False
    else:
        role_title = clean_role
        use_role = True
        
    if len(clean_company) > 50 or clean_company.lower() in ("company", "employer", ""):
        company_title = "your company"
        use_company = False
    else:
        company_title = clean_company
        use_company = True

    subject = f"Application | Software Engineer/Developer | Immediate Joiner "

    # Build a clean opening phrase to prevent grammatically broken sentences
    if use_role and use_company:
        intro_phrase = f"opening for the {role_title} role at {company_title}"
    elif use_company:
        intro_phrase = f"engineering opportunities at {company_title}"
    else:
        intro_phrase = "engineering opportunities at your company"

    # Constant 3rd paragraph technical stack description
    tech_sentence = (
        "My expertise spans full-stack development with React.js, Node.js, Express.js, FastAPI, Django, "
        "TypeScript, PostgreSQL, PHP and MongoDB, complemented by AI-assisted engineering, "
        "Prompt Engineering, LLM integration, OpenAI APIs, RAG concepts, and intelligent workflow automation."
    )

    closings = [
        "Please find my resume attached for your review. I would welcome the opportunity to discuss how my experience and technical expertise can contribute to your engineering team.",
        "I've attached my resume and would be happy to discuss how I can contribute.",
        "Thank you for considering my application. I look forward to hearing from you.",
        "I would welcome the opportunity to discuss how my experience aligns with your team's goals."
    ]
    email_key = recruiter.get("email") or ""
    idx = sum(ord(c) for c in email_key) % len(closings)
    closing_text = closings[idx]

    body = f"""{salutation}

I am excited about the opportunity to contribute to your engineering team and would appreciate being considered for any Full Stack, Backend, AI Engineering, or Software Engineering role that matches my background.

I am an AI Full Stack Product Engineer with 1+ year of professional experience. Over the past year, I have gained hands-on experience building production-ready applications and delivering live enterprise projects. By designing secure REST APIs and robust backend services, I have contributed to enterprise software and cloud-native applications. I enjoy cross-functional collaboration and managing the end-to-end software development lifecycle.

{tech_sentence}

Professional Summary

• Experience: 1+ Year
• Current Role: AI Full Stack Product Engineer
• Current CTC: ₹3.5 LPA
• Expected CTC: Negotiable
• Notice Period: Immediate
• Current Location: Bengaluru

{closing_text}

Kind Regards,

Santhosh B

Mobile: +91 9952204644

Email: san0thosh08@gmail.com

LinkedIn: https://www.linkedin.com/in/santhosh-b-8333822a8

GitHub: https://github.com/santhosh801"""

    return subject, body

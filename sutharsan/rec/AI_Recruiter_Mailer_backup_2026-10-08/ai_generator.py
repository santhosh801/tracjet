import os
import json
from openai import OpenAI

PROFILE = {
    "Name": "Santhosh B",
    "Current Role": "AI Full Stack Product Engineer",
    "Experience": "1+ Year",
    "Skills": ["React.js", "Node.js", "Express.js", "Python", "FastAPI", "JavaScript", "TypeScript", "PostgreSQL", "MongoDB", "REST APIs", "Docker", "Git", "GitHub", "OpenAI", "LLMs", "LangChain", "LangGraph", "RAG", "Prompt Engineering", "Agentic AI", "MCP"]
}

def get_client(api_key):
    return OpenAI(api_key=api_key)

def extract_recruiters(api_key, raw_text):
    client = get_client(api_key)
    prompt = f'''
    You are an AI assistant helping a job seeker. 
    Read the following raw text (which might be from a CSV, HTML, TXT, or pasted LinkedIn export).
    Extract ALL the recruiter posts/jobs you can find in it.
    
    For EACH job/recruiter post, extract these fields (leave empty if not found):
    - "recruiter_name"
    - "company"
    - "email"
    - "job_title"
    - "location"
    - "experience"
    - "skills_required"
    - "jd" (the full job description text)

    Return a JSON object with a single key "recruiters" which is a list of these objects.
    
    Raw Text:
    {raw_text[:8000]}  # Limiting length to prevent token overflow
    '''
    
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        response_format={ "type": "json_object" }
    )
    
    return json.loads(response.choices[0].message.content).get("recruiters", [])

def analyze_jd(api_key, jd_text):
    client = get_client(api_key)
    prompt = f'''
    Analyze the following Job Description against this profile:
    {json.dumps(PROFILE, indent=2)}

    JD:
    {jd_text}

    Return a JSON object with these EXACT keys:
    "match_percentage" (integer 0-100),
    "matched_skills" (list of strings),
    "missing_skills" (list of strings),
    "category" (string e.g. 'AI Engineer', 'Full Stack', 'Backend'),
    "recommendation" (short string on whether to apply)
    '''
    
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        response_format={ "type": "json_object" }
    )
    
    return json.loads(response.choices[0].message.content)

def generate_email(api_key, recruiter_data, analysis_data, signature):
    client = get_client(api_key)
    prompt = f'''
    Write a highly personalized, professional, and ATS-friendly email to a recruiter.
    Recruiter Name: {recruiter_data.get('recruiter_name', 'Hiring Manager')}
    Company: {recruiter_data.get('company', 'your company')}
    Job Title: {recruiter_data.get('job_title', 'the role')}
    
    My Profile Name: Santhosh B
    My Role: AI Full Stack Product Engineer
    Matched Skills for this role: {', '.join(analysis_data.get('matched_skills', []))}
    
    Guidelines:
    - Maximum 350 words.
    - Mention only the matched skills relevant to their job description.
    - Do not claim skills I do not have.
    - Be human-sounding.
    - End the email with this signature:
    {signature}
    
    Return a JSON object with:
    "subject": "Email Subject Line",
    "body": "Full email body"
    '''
    
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        response_format={ "type": "json_object" }
    )
    
    return json.loads(response.choices[0].message.content)

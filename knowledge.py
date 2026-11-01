"""
Shared domain vocabulary for Tracjet.

Used by the resume analyzer, JD analyzer, template matcher, email composer
and quality checker so every module recognises skills, concepts, cities and
industries the same way.  Nothing in here is candidate-specific.
"""
import re
from functools import lru_cache

APP_NAME = "Tracjet"
APP_TAGLINE = "AI Recruiter Email Platform"

# ── Skills ────────────────────────────────────────────────────────────────
# canonical name -> aliases (matched case-insensitively on word boundaries)
TECH_SKILLS = {
    "Python": ["python"], "Java": ["java"], "JavaScript": ["javascript", "js"],
    "TypeScript": ["typescript"], "React.js": ["react", "reactjs", "react.js"],
    "Angular": ["angular", "angularjs"], "Vue.js": ["vue", "vuejs", "vue.js"],
    "Node.js": ["node", "nodejs", "node.js"], "Express.js": ["express.js", "expressjs"],
    "Next.js": ["next.js", "nextjs"], "Django": ["django"], "Flask": ["flask"],
    "FastAPI": ["fastapi"], "Spring Boot": ["spring boot", "springboot"],
    "Hibernate": ["hibernate"], ".NET": [".net", "dotnet", "asp.net"], "C#": ["c#"],
    "C++": ["c++"], "Golang": ["golang"], "PHP": ["php"], "Laravel": ["laravel"],
    "Kotlin": ["kotlin"], "Flutter": ["flutter"], "React Native": ["react native"],
    "Android": ["android"], "iOS": ["ios"], "HTML": ["html", "html5"], "CSS": ["css", "css3"],
    "Tailwind CSS": ["tailwind"], "SQL": ["sql"], "MySQL": ["mysql"],
    "PostgreSQL": ["postgresql", "postgres"], "MongoDB": ["mongodb", "mongo"],
    "Redis": ["redis"], "Elasticsearch": ["elasticsearch"], "Kafka": ["kafka"],
    "GraphQL": ["graphql"], "REST APIs": ["rest api", "rest apis", "restful", "restful apis"],
    "Microservices": ["microservices", "microservice"], "AWS": ["aws", "amazon web services"],
    "Azure": ["azure"], "GCP": ["gcp", "google cloud"], "Docker": ["docker"],
    "Kubernetes": ["kubernetes", "k8s"], "Terraform": ["terraform"], "Jenkins": ["jenkins"],
    "CI/CD": ["ci/cd", "cicd"], "Git": ["git"], "GitHub": ["github"], "Linux": ["linux"],
    "Selenium": ["selenium"], "Jest": ["jest"], "Cypress": ["cypress"],
    "Machine Learning": ["machine learning"], "Deep Learning": ["deep learning"],
    "NLP": ["nlp", "natural language processing"], "TensorFlow": ["tensorflow"],
    "PyTorch": ["pytorch"], "Pandas": ["pandas"], "NumPy": ["numpy"], "Spark": ["pyspark", "apache spark"],
    "Snowflake": ["snowflake"], "Databricks": ["databricks"], "Airflow": ["airflow"],
    "ETL": ["etl"], "Figma": ["figma"], "Agile": ["agile"], "Scrum": ["scrum"],
    "RAG": ["rag", "retrieval augmented generation"], "LangChain": ["langchain"],
    "LangGraph": ["langgraph"], "MCP": ["mcp"], "Data Structures": ["data structures"],
}
# Case-sensitive tech terms that are also common English words.
TECH_SKILLS_CASED = {"Go": ["Go"], "Ruby": ["Ruby"], "Rust": ["Rust"], "Swift": ["Swift"],
                     "Spring": ["Spring"], "R": ["R"]}

CRM_TOOLS = {
    "Salesforce": ["salesforce", "sfdc"], "HubSpot": ["hubspot"], "Zoho CRM": ["zoho crm", "zoho"],
    "LeadSquared": ["leadsquared", "lead squared"], "Freshsales": ["freshsales", "freshworks crm"],
    "Pipedrive": ["pipedrive"], "Microsoft Dynamics": ["microsoft dynamics", "dynamics 365", "ms dynamics"],
    "Odoo": ["odoo"], "Kylas": ["kylas"], "Bitrix24": ["bitrix24", "bitrix"], "SugarCRM": ["sugarcrm"],
    "CRM": ["crm", "crm tools", "crm software"],
}

AI_TOOLS = {
    "ChatGPT": ["chatgpt", "chat gpt"], "OpenAI": ["openai", "openai api", "openai apis"],
    "GitHub Copilot": ["copilot", "github copilot"], "Gemini": ["gemini"], "Claude": ["claude"],
    "Midjourney": ["midjourney"], "Perplexity": ["perplexity"], "Generative AI": ["generative ai", "genai", "gen ai"],
    "LLMs": ["llm", "llms", "large language models", "large language model"],
    "Prompt Engineering": ["prompt engineering"], "AI Agents": ["ai agents", "agentic ai"],
}

GENERAL_TOOLS = {
    "MS Excel": ["excel", "ms excel", "microsoft excel"], "MS Office": ["ms office", "microsoft office"],
    "PowerPoint": ["powerpoint"], "Google Sheets": ["google sheets"], "Google Workspace": ["google workspace", "g suite"],
    "Power BI": ["power bi", "powerbi"], "Tableau": ["tableau"], "Jira": ["jira"], "Trello": ["trello"],
    "Asana": ["asana"], "Canva": ["canva"], "Tally": ["tally"], "SAP": ["sap"],
    "LinkedIn Sales Navigator": ["sales navigator", "linkedin sales navigator"],
    "Apollo.io": ["apollo.io"], "Lusha": ["lusha"], "ZoomInfo": ["zoominfo"], "Mailchimp": ["mailchimp"],
    "Notion": ["notion"], "Slack": ["slack"],
}

BUSINESS_SKILLS = {
    "Business Development": ["business development", "biz dev"],
    "Sales": ["sales"], "Inside Sales": ["inside sales"], "B2B Sales": ["b2b sales", "b2b"],
    "B2C Sales": ["b2c sales", "b2c"], "Lead Generation": ["lead generation", "lead gen", "prospecting"],
    "Lead Conversion": ["lead conversion", "lead closure", "converting leads", "conversion of leads"],
    "Cold Calling": ["cold calling", "cold calls", "cold-calling"],
    "Client Relationship Management": ["client relationship management", "client relationship", "client relationships",
                                       "client relations", "relationship management"],
    "Customer Relationship Management": ["customer relationship management", "customer relationship", "customer relationships"],
    "Account Management": ["account management", "key account management", "key accounts", "kam"],
    "Negotiation": ["negotiation", "negotiating", "negotiations"],
    "Market Research": ["market research", "market analysis"],
    "Pipeline Management": ["pipeline management", "sales pipeline", "pipeline"],
    "Revenue Growth": ["revenue growth", "revenue generation"],
    "Team Leadership": ["team leadership", "team lead", "team leader", "leading a team", "led a team"],
    "Team Management": ["team management", "people management", "managing a team", "managed a team"],
    "Stakeholder Management": ["stakeholder management", "stakeholders"],
    "Customer Success": ["customer success"], "Customer Service": ["customer service"],
    "Customer Support": ["customer support"], "Communication": ["communication", "communication skills"],
    "Presentation Skills": ["presentation skills", "presentations"],
    "Upselling": ["upselling", "up-selling", "upsell"], "Cross-selling": ["cross-selling", "cross selling", "cross-sell"],
    "Channel Sales": ["channel sales", "channel partners"], "Partnerships": ["partnerships", "strategic partnerships"],
    "Sales Forecasting": ["sales forecasting", "forecasting"], "Strategic Planning": ["strategic planning"],
    "Recruitment": ["recruitment", "recruiting"], "Talent Acquisition": ["talent acquisition"],
    "Onboarding": ["onboarding"], "Training": ["training"], "Mentoring": ["mentoring", "mentored"],
    "Project Management": ["project management"], "Product Management": ["product management"],
    "Operations Management": ["operations management"], "Digital Marketing": ["digital marketing"],
    "SEO": ["seo"], "Social Media Marketing": ["social media marketing", "social media"],
    "Email Marketing": ["email marketing"], "Content Marketing": ["content marketing"],
    "Data Analysis": ["data analysis", "data analytics"], "Reporting": ["reporting", "mis reports", "mis"],
    "Vendor Management": ["vendor management"], "Proposal Writing": ["proposal writing", "proposals", "rfp"],
    "Product Demonstrations": ["product demos", "product demonstrations", "product demo"],
    "Contract Negotiation": ["contract negotiation"], "Customer Retention": ["customer retention", "client retention", "retention"],
    "Problem Solving": ["problem solving", "problem-solving"], "Time Management": ["time management"],
}

SKILL_CATEGORIES = {
    "technical": TECH_SKILLS, "crm": CRM_TOOLS, "ai": AI_TOOLS,
    "tools": GENERAL_TOOLS, "business": BUSINESS_SKILLS,
}

# ── Concepts (used for similarity, scoring and highlight labels) ─────────
# A keyword ending in '*' matches as a prefix (stem).
CONCEPTS = {
    "Business Development": ("sales", ["business development", "bde", "bdm", "new business", "market expansion",
                                       "partnership*", "new accounts", "new clients", "business growth"]),
    "Sales & Revenue Targets": ("sales", ["sales", "target*", "quota*", "revenue", "closing", "close deals", "deal*",
                                          "sales cycle", "achiev*", "sold"]),
    "Lead Generation & Conversion": ("sales", ["lead*", "prospect*", "cold call*", "inbound", "outbound",
                                               "conversion*", "convert*", "funnel", "pipeline", "follow-up*", "follow up*"]),
    "Client Relationship Management": ("customer", ["client*", "relationship*", "account management", "key account*",
                                                    "rapport", "retention", "repeat business", "referral*"]),
    "Customer Success & Support": ("customer", ["customer*", "customer success", "support", "satisfaction", "csat",
                                                "nps", "escalation*", "resolution", "service", "onboard*"]),
    "CRM & Sales Tools": ("sales", ["crm", "salesforce", "hubspot", "zoho", "leadsquared", "pipedrive", "freshsales",
                                    "dynamics", "sales navigator"]),
    "Negotiation & Closing": ("sales", ["negotiat*", "closing", "closure*", "contract*", "pricing", "proposal*",
                                        "quotation*", "objection*"]),
    "Team Leadership": ("leadership", ["lead a team", "led a team", "team lead*", "leadership", "mentor*", "supervis*",
                                       "coach*", "people management", "team of", "managed a team", "managing a team",
                                       "team management", "team productivity", "led"]),
    "Strategy & Planning": ("management", ["strateg*", "planning", "forecast*", "business plan*", "market research",
                                           "go-to-market", "gtm", "competitor*"]),
    "Communication & Presentation": ("general", ["communication*", "presentation*", "present*", "stakeholder*",
                                                 "demo*", "interpersonal"]),
    "Marketing": ("marketing", ["marketing", "campaign*", "seo", "social media", "brand*", "content", "digital marketing"]),
    "Recruitment & HR": ("hr", ["recruit*", "talent acquisition", "hiring", "sourcing", "screening", "payroll",
                                "human resources", "hr"]),
    "Operations & Process": ("operations", ["operation*", "process*", "workflow*", "efficiency", "productivity", "sop*",
                                            "vendor*", "logistics", "coordination"]),
    "Software Development": ("tech", ["software", "software development", "coding", "programming", "sdlc",
                                      "code", "developer*", "web application*", "software engineer*"]),
    "Frontend Development": ("tech", ["frontend", "front-end", "front end", "react*", "angular", "vue", "ui",
                                      "html", "css", "javascript", "typescript", "responsive"]),
    "Backend Development": ("tech", ["backend", "back-end", "back end", "api*", "server*", "microservice*",
                                     "database*", "node*", "django", "spring", "java", "python", "fastapi"]),
    "Full Stack Development": ("tech", ["full stack", "fullstack", "full-stack", "mern", "mean", "end-to-end"]),
    "Cloud & DevOps": ("tech", ["aws", "azure", "gcp", "cloud", "docker", "kubernetes", "devops", "ci/cd",
                                "deployment*", "terraform", "jenkins"]),
    "Data & Analytics": ("data", ["data", "analytic*", "sql", "reporting", "dashboard*", "power bi", "tableau",
                                  "excel", "insight*", "metrics", "kpi*", "mis"]),
    "AI & Machine Learning": ("tech", ["ai", "machine learning", "ml", "llm*", "generative ai", "genai", "nlp",
                                       "rag", "langchain", "deep learning", "chatgpt", "openai"]),
    "Quality Assurance & Testing": ("tech", ["testing", "qa", "quality assurance", "test case*", "automation testing",
                                             "selenium", "bug*"]),
    "Project & Product Management": ("management", ["project management", "product management", "agile", "scrum",
                                                    "roadmap*", "delivery", "milestone*", "sprint*"]),
    "Training & Mentoring": ("leadership", ["training", "trained", "mentor*", "coach*", "knowledge transfer", "upskill*"]),
}

CONCEPT_PHRASES = {
    "Business Development": "business development", "Sales & Revenue Targets": "sales targets",
    "Lead Generation & Conversion": "lead generation and conversion",
    "Client Relationship Management": "client relationships", "Customer Success & Support": "customer success",
    "CRM & Sales Tools": "CRM-driven sales", "Negotiation & Closing": "negotiation and closing",
    "Team Leadership": "team leadership", "Strategy & Planning": "planning and strategy",
    "Communication & Presentation": "communication", "Marketing": "marketing", "Recruitment & HR": "recruitment",
    "Operations & Process": "operations", "Software Development": "software development",
    "Frontend Development": "frontend development", "Backend Development": "backend development",
    "Full Stack Development": "full stack development", "Cloud & DevOps": "cloud and DevOps",
    "Data & Analytics": "data and analytics", "AI & Machine Learning": "AI/ML",
    "Quality Assurance & Testing": "quality assurance", "Project & Product Management": "project delivery",
    "Training & Mentoring": "training and mentoring",
}

# Profile keys derived by the analyzer (categories, not resume facts) — never used to justify claims
DERIVED_PROFILE_KEYS = {"domain_knowledge", "job_families", "keywords"}

GENERIC_CAPS = {"years", "year", "experience", "immediate", "joiner", "hiring", "team", "kind", "regards", "dear",
                "application", "key", "highlights", "role", "position", "opportunity", "expected", "ctc",
                "availability", "negotiable", "current", "linkedin", "hello", "hi", "thank", "you", "best",
                "warm", "sincerely", "here", "my", "the", "for", "and", "of", "in", "at", "with", "manager",
                "lead", "executive", "engineer", "developer", "notice", "period", "days", "months", "resume"}

JOB_FAMILY_BY_CONCEPT = {
    "Business Development": "Business Development / Sales",
    "Sales & Revenue Targets": "Business Development / Sales",
    "Lead Generation & Conversion": "Inside Sales / Lead Generation",
    "Client Relationship Management": "Account Management / Client Servicing",
    "Customer Success & Support": "Customer Success / Customer Support",
    "CRM & Sales Tools": "Sales Operations / CRM",
    "Negotiation & Closing": "Business Development / Sales",
    "Team Leadership": "Team Lead / Management",
    "Strategy & Planning": "Strategy / Business Planning",
    "Marketing": "Marketing",
    "Recruitment & HR": "Recruitment / HR",
    "Operations & Process": "Operations",
    "Software Development": "Software Engineering",
    "Frontend Development": "Frontend Engineering",
    "Backend Development": "Backend Engineering",
    "Full Stack Development": "Full Stack Engineering",
    "Cloud & DevOps": "Cloud / DevOps",
    "Data & Analytics": "Data / Analytics",
    "AI & Machine Learning": "AI / Machine Learning",
    "Quality Assurance & Testing": "Quality Assurance",
    "Project & Product Management": "Project / Product Management",
    "Training & Mentoring": "Training / Learning & Development",
}

# ── Locations ────────────────────────────────────────────────────────────
CITIES = {
    "Bengaluru": ["bengaluru", "bangalore", "blr", "bengalore", "banglore"],
    "Chennai": ["chennai", "madras"],
    "Hyderabad": ["hyderabad", "secunderabad"],
    "Pune": ["pune"],
    "Mumbai": ["mumbai", "bombay", "navi mumbai", "thane"],
    "Delhi NCR": ["delhi ncr", "new delhi", "delhi", "ncr", "gurgaon", "gurugram", "noida", "greater noida",
                  "ghaziabad", "faridabad"],
    "Kolkata": ["kolkata", "calcutta"],
    "Ahmedabad": ["ahmedabad"],
    "Kochi": ["kochi", "cochin", "ernakulam"],
    "Coimbatore": ["coimbatore"],
    "Thiruvananthapuram": ["thiruvananthapuram", "trivandrum"],
    "Mysuru": ["mysuru", "mysore"],
    "Mangaluru": ["mangaluru", "mangalore"],
    "Jaipur": ["jaipur"], "Chandigarh": ["chandigarh", "mohali"], "Indore": ["indore"],
    "Bhubaneswar": ["bhubaneswar"], "Visakhapatnam": ["visakhapatnam", "vizag"],
    "Lucknow": ["lucknow"], "Nagpur": ["nagpur"], "Madurai": ["madurai"], "Vadodara": ["vadodara", "baroda"],
    "Surat": ["surat"], "Dubai": ["dubai"], "Singapore": ["singapore"], "London": ["london"],
    "Remote": ["remote", "work from home", "wfh", "work-from-home", "fully remote"],
}
DEFAULT_FILTER_CITIES = ["Bengaluru", "Chennai", "Hyderabad", "Pune", "Mumbai", "Delhi NCR", "Remote"]

EXPERIENCE_BUCKETS = [
    ("All Experience", None, None),
    ("0–2 years", 0, 2), ("2–4 years", 2, 4), ("4–6 years", 4, 6),
    ("6–8 years", 6, 8), ("8+ years", 8, None),
]

INDUSTRIES = {
    "IT Services": ["it services", "software services", "it company"], "SaaS": ["saas"],
    "EdTech": ["edtech", "ed-tech", "education technology"], "FinTech": ["fintech", "fin-tech"],
    "Banking & Financial Services": ["banking", "bank", "nbfc", "bfsi", "financial services"],
    "Insurance": ["insurance"], "Healthcare": ["healthcare", "hospital", "medical"],
    "Pharma": ["pharma", "pharmaceutical"], "Real Estate": ["real estate", "realty"],
    "Retail": ["retail"], "E-commerce": ["e-commerce", "ecommerce"], "Telecom": ["telecom"],
    "Manufacturing": ["manufacturing"], "Logistics": ["logistics", "supply chain"],
    "Hospitality": ["hospitality", "hotel"], "Automobile": ["automobile", "automotive"],
    "BPO / KPO": ["bpo", "kpo", "call center", "call centre"], "Media & Advertising": ["advertising", "media"],
    "FMCG": ["fmcg"], "Consulting": ["consulting"], "Staffing & Recruitment": ["staffing"],
    "Education": ["education", "school", "university"], "Travel": ["travel"],
}

LANGUAGES = ["English", "Hindi", "Tamil", "Telugu", "Kannada", "Malayalam", "Marathi", "Bengali", "Gujarati",
             "Punjabi", "Urdu", "Odia", "French", "German", "Spanish", "Arabic", "Japanese", "Mandarin"]

DEGREE_PATTERN = re.compile(
    r"\b(b\.?\s?e\b|b\.?\s?tech|m\.?\s?tech|b\.?\s?sc|m\.?\s?sc|b\.?\s?com|m\.?\s?com|bba|mba|bca|mca|b\.?\s?a\b|"
    r"m\.?\s?a\b|ph\.?\s?d|bachelor|master|diploma|pgdm|post graduate|higher secondary|hsc|ssc|12th|10th|degree)",
    re.IGNORECASE)

ROLE_WORDS = {
    "executive", "manager", "engineer", "developer", "analyst", "lead", "associate", "intern", "consultant",
    "specialist", "officer", "coordinator", "representative", "head", "director", "designer", "administrator",
    "architect", "trainee", "advisor", "assistant", "supervisor", "recruiter", "tester", "programmer", "scientist",
    "strategist", "partner", "agent", "counsellor", "counselor", "owner", "vp", "president", "sde", "fsd", "bde",
    "bdm", "qa", "devops", "fresher", "freshers", "telecaller", "caller", "expert", "member", "staff", "writer",
    "marketer", "accountant", "technician", "operator", "generalist", "hrbp", "sdr", "bdr", "ae", "kam", "cxo",
    "ceo", "cto", "cfo", "principal", "chief", "mentor", "trainer", "instructor", "teacher", "faculty",
}

COMPANY_HINTS = {"pvt", "private", "ltd", "limited", "inc", "llc", "llp", "technologies", "technology", "solutions",
                 "services", "corp", "corporation", "company", "group", "labs", "systems", "software", "consulting",
                 "consultancy", "bank", "infotech", "enterprises", "industries", "global", "digital", "ventures",
                 "networks", "international", "co.", "tech", "analytics", "media", "studios", "healthcare"}

GENERIC_EMAIL_DOMAINS = {"gmail", "yahoo", "outlook", "hotmail", "rediffmail", "rediff", "icloud", "live", "aol",
                         "protonmail", "proton", "zoho", "ymail", "msn", "mail", "gmx", "yandex"}

STOPWORDS = set("""a an the and or but if of to in on at for with by from as is are was were be been being this that
these those it its we our us you your they their them he she his her i me my mine will would shall should can could
may might must do does did done have has had having not no nor so than too very just also into about over under
again further then once here there when where why how all any both each few more most other some such only own same
what which who whom up down out off above below between through during before after while per via etc using use
used able across within without upon including include includes like well new role job position opening openings
candidate candidates looking hiring hire apply interested share send resume cv email mail please contact required
requirement requirements must good strong excellent knowledge experience experienced years year yrs work working
team company immediate joiner joiners location salary ctc lpa based opportunity opportunities day days""".split())


# ── Matching helpers ─────────────────────────────────────────────────────
@lru_cache(maxsize=4096)
def term_regex(term: str, case_sensitive: bool = False) -> re.Pattern:
    """Word-boundary regex for a term.  A trailing '*' turns it into a prefix match."""
    stem = term.endswith("*")
    core = re.escape(term[:-1] if stem else term).replace(r"\ ", r"[\s\-]+")
    tail = r"[A-Za-z]*" if stem else r"(?![A-Za-z0-9])"
    flags = 0 if case_sensitive else re.IGNORECASE
    return re.compile(r"(?<![A-Za-z0-9])" + core + tail, flags)


def count_term(term: str, text: str, case_sensitive: bool = False) -> int:
    return len(term_regex(term, case_sensitive).findall(text or ""))


def has_term(term: str, text: str, case_sensitive: bool = False) -> bool:
    return bool(term_regex(term, case_sensitive).search(text or ""))


def find_vocab(text: str, vocab: dict, case_sensitive: bool = False) -> list[str]:
    """Return canonical names from a vocab dict that occur in text (in vocab order)."""
    found = []
    for canonical, aliases in vocab.items():
        if any(has_term(a, text, case_sensitive) for a in aliases):
            found.append(canonical)
    return found


@lru_cache(maxsize=1)
def all_skill_vocab() -> dict:
    merged = {}
    for vocab in (TECH_SKILLS, CRM_TOOLS, AI_TOOLS, GENERAL_TOOLS, BUSINESS_SKILLS):
        merged.update(vocab)
    return merged


def find_skills(text: str) -> dict:
    """Categorised skill detection over free text."""
    return {
        "technical": find_vocab(text, TECH_SKILLS) + find_vocab(text, TECH_SKILLS_CASED, case_sensitive=True),
        "crm": find_vocab(text, CRM_TOOLS),
        "ai": find_vocab(text, AI_TOOLS),
        "tools": find_vocab(text, GENERAL_TOOLS),
        "business": find_vocab(text, BUSINESS_SKILLS),
    }


def skill_supported(canonical: str, text: str) -> bool:
    """True when any alias of a canonical skill appears in text."""
    aliases = all_skill_vocab().get(canonical) or TECH_SKILLS_CASED.get(canonical) or [canonical]
    cased = canonical in TECH_SKILLS_CASED
    return any(has_term(a, text, cased) for a in aliases)


def concept_vector(text: str) -> dict:
    """Concept -> hit count for a block of text."""
    vec = {}
    for name, (_family, keywords) in CONCEPTS.items():
        hits = sum(count_term(k, text) for k in keywords)
        if hits:
            vec[name] = hits
    return vec


def family_vector(text: str) -> dict:
    fam = {}
    for name, hits in concept_vector(text).items():
        f = CONCEPTS[name][0]
        fam[f] = fam.get(f, 0) + hits
    return fam


def cosine(a: dict, b: dict) -> float:
    if not a or not b:
        return 0.0
    import math
    dot = sum(a[k] * b.get(k, 0) for k in a)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


def tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z][a-z0-9+#./]*[a-z0-9+#]|[a-z]", (text or "").lower())
            if t not in STOPWORDS and len(t) > 1]


def token_vector(text: str) -> dict:
    vec = {}
    for t in tokens(text):
        vec[t] = vec.get(t, 0) + 1
    return vec


@lru_cache(maxsize=1024)
def _detect_cities_cached(text: str) -> tuple:
    hits = []
    for canonical, aliases in CITIES.items():
        positions = [m.start() for a in aliases for m in term_regex(a).finditer(text)]
        if positions:
            hits.append((min(positions), canonical))
    return tuple(c for _, c in sorted(hits))


def detect_cities(text: str) -> list[str]:
    """Canonical cities mentioned in text, in order of first appearance."""
    return list(_detect_cities_cached(text or ""))


@lru_cache(maxsize=512)
def skills_in(text: str) -> frozenset:
    """Every canonical skill (any category) whose alias appears in text — cached per text."""
    found = {k for k, aliases in all_skill_vocab().items() if any(has_term(a, text) for a in aliases)}
    found |= {k for k, aliases in TECH_SKILLS_CASED.items() if any(has_term(a, text, True) for a in aliases)}
    return frozenset(found)


def find_industries(text: str) -> list[str]:
    return find_vocab(text, INDUSTRIES)


def is_role_like(text: str) -> bool:
    words = set(re.findall(r"[a-z]+", (text or "").lower()))
    return bool(words & ROLE_WORDS) or "business development" in (text or "").lower()

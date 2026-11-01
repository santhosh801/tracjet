"""Fictional test data (no real candidate PII)."""

BD_RESUME = """ASHA RAMAN
Senior Business Development Executive
Bengaluru, Karnataka | asha.raman.test@example.org | +91 90000 11111

PROFESSIONAL SUMMARY
Results-driven Business Development professional with 4.9+ years of experience in B2B sales, lead generation,
client relationship management and team leadership across EdTech and SaaS companies.

WORK EXPERIENCE
Senior Business Development Executive | BrightPath Learning Pvt Ltd | Jan 2023 - Present
• Achieved 120% of quarterly sales target for four consecutive quarters
• Managed inbound and outbound lead pipeline using Salesforce CRM
• Led a team of 6 executives and improved team productivity by 30%
• Negotiated enterprise contracts and closed deals with institutional clients
• Built long-term client relationships resulting in 95% customer satisfaction

Business Development Executive | CloudNova Solutions | Jun 2020 - Dec 2022
• Generated qualified leads through cold calling, LinkedIn Sales Navigator and email campaigns
• Converted 25% of demo leads into paying customers
• Conducted product demonstrations for SME clients
• Maintained CRM records and weekly sales reports in HubSpot

SKILLS
Business Development, B2B Sales, Lead Generation, Client Relationship Management, Negotiation,
Salesforce, HubSpot, MS Excel, ChatGPT, Team Leadership

EDUCATION
MBA (Marketing) - Christ University, 2020
B.Com - Mount Carmel College, 2018

CERTIFICATIONS
HubSpot Inbound Sales Certification

LANGUAGES
English, Hindi, Kannada, Tamil
"""

DEV_RESUME = """RAVI KUMAR
Full Stack Developer
Chennai | ravi.kumar.test@example.org | +91 98888 22222

SUMMARY
Full Stack Developer with 3 years of experience building web applications with React.js, Node.js and PostgreSQL.

EXPERIENCE
Software Engineer | Acme Technologies | Mar 2022 - Present
- Built REST APIs in Node.js and Express.js serving 50,000 daily users
- Developed responsive React.js frontends with TypeScript
- Containerised services with Docker and deployed on AWS
- Reduced API latency by 40% through query optimisation in PostgreSQL
Junior Developer | Pixel Labs | Jan 2021 - Feb 2022
- Implemented UI components in React.js and wrote Jest unit tests

SKILLS
JavaScript, TypeScript, React.js, Node.js, Express.js, PostgreSQL, MongoDB, Docker, AWS, Git

EDUCATION
B.E. Computer Science - Anna University, 2020
"""

JD_BD = """Feed post
Neha Kapoor
Talent Acquisition at Orbit EdTech
We're Hiring: Business Development Manager
Company: Orbit EdTech
Location: Bengaluru (Hybrid)
Experience: 3-5 years

Key Responsibilities:
• Drive new business through inbound and outbound lead generation
• Own the sales pipeline in CRM (Salesforce preferred) and achieve monthly revenue targets
• Build strong client relationships with institutions and negotiate contracts
• Convert qualified leads into paying customers

Requirements:
• Proven B2B sales experience with target achievement
• Excellent negotiation and communication skills
• Experience with CRM tools

Interested candidates can share their CV at neha.kapoor@orbitedtech.test
"""

JD_FSD = """We are hiring a Full Stack Developer at Zenith Software!
Location: Chennai
Experience: 2-4 years
Responsibilities:
- Build REST APIs using Node.js and Express.js
- Develop React.js frontends with TypeScript
- Work with PostgreSQL and MongoDB, deploy with Docker on AWS
Must have: JavaScript, React.js, Node.js, SQL
Good to have: Kubernetes, GraphQL
Send your resume to careers@zenithsoft.test
"""

JD_TL = """Hiring: Team Lead - Customer Success
Company: Helio SaaS
Location: Hyderabad
Experience: 6-8 years
Responsibilities:
- Lead and mentor a team of 10 customer success managers
- Own team productivity, coaching and performance reviews
- Drive customer satisfaction, retention and escalation management
- Plan team targets and report KPIs to leadership
Contact: Arjun Mehta
Email: arjun.mehta@heliosaas.test
"""

JD_PY = """Hiring: Python Data Engineer
Company: DataForge
Location: Pune
Experience: 4-6 years
Must have: Python, Apache Spark, Airflow, Snowflake, Kafka
Share CV: jobs@dataforge.test
"""

TEMPLATES = [
    {"slot": 1, "name": "Software Engineer", "role_category": "Software Engineering",
     "example_subject": "Application for Software Engineer | 3 Years Experience | Immediate Joiner",
     "example_body": """Dear Hiring Team,

I am writing to express my interest in the Software Engineer role. I enjoy building reliable software.

Key highlights:
• Built backend services and REST APIs
• Wrote unit tests and improved code quality
• Worked with Git and CI/CD pipelines
• Collaborated with product teams in Agile sprints
• Debugged production issues

Thank you for your time and consideration.

Kind Regards,
Someone"""},
    {"slot": 2, "name": "Full Stack Developer", "role_category": "Full Stack Engineering",
     "example_subject": "Full Stack Developer Application – React.js / Node.js – Immediate Joiner",
     "example_body": """Hi Hiring Team,

I came across your opening for a Full Stack Developer and would love to be considered.

Highlights of my experience:
- Built React.js frontends and Node.js APIs
- Designed PostgreSQL and MongoDB schemas
- Deployed apps with Docker on AWS
- Implemented authentication and REST APIs
- Wrote Jest tests for UI components

I would be glad to connect at your convenience.

Kind Regards,
Someone"""},
    {"slot": 3, "name": "Business Development", "role_category": "Business Development / Sales",
     "example_subject": "Application for Business Development Manager | 5 Years Experience | Immediate Joiner",
     "example_body": """Dear Hiring Team,

I am writing to express my interest in the Business Development Manager opportunity at Globex Corp. I have 5 years of Python experience.

Here is a quick snapshot of my experience:
• Business Development: Generated new business through outbound prospecting
• Lead Conversion: Converted inbound leads into customers
• Client Relationships: Managed key client accounts
• Sales Targets: Consistently exceeded quarterly sales targets
• CRM: Maintained pipeline hygiene in CRM

I believe I can add value to your sales team from day one.

Kind Regards,
Someone"""},
    {"slot": 4, "name": "Team Lead", "role_category": "Team Lead / Management",
     "example_subject": "Application for Team Lead role | Immediate Joiner",
     "example_body": """Dear Hiring Team,

I am excited to apply for the Team Lead position.

Leadership highlights:
• Led and mentored a team of executives
• Improved team productivity through coaching
• Set team targets and tracked KPIs
• Handled escalations and performance reviews
• Built a culture of accountability

Thank you for considering my application.

Kind Regards,
Someone"""},
    {"slot": 5, "name": "Customer Success", "role_category": "Customer Success / Account Management",
     "example_subject": "Customer Success Application | Immediate Joiner",
     "example_body": """Hello Hiring Team,

I am interested in the Customer Success opening.

What I bring:
• Customer onboarding and support
• Customer satisfaction and retention
• Escalation handling
• Account management
• Customer feedback analysis

Looking forward to hearing from you.

Kind Regards,
Someone"""},
]

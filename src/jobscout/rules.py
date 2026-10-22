"""Bundled web/CMS/search career-profile rules.

The scoring engine is intentionally deterministic and explainable. These rules are
kept separate from orchestration so alternate career profiles can be introduced
without rewriting source adapters.
"""

# ---------------------------------------------------------------------------
# Matching model
# ---------------------------------------------------------------------------
# Exact phrase/token matching is deliberate. v0.1 used substring matching, so
# "cro" matched "cross-functional" and "geo" matched unrelated words.
# That produced nonsensical 80% matches for accounting and engineering roles.

TITLE_TERMS = {
    "aeo": 30,
    "geo": 30,
    "answer engine optimization": 30,
    "generative engine optimization": 30,
    "technical seo": 28,
    "search engine optimization specialist": 28,
    "search engine optimization": 26,
    "seo specialist": 26,
    "seo manager": 26,
    "seo strategist": 26,
    "search strategist": 24,
    "website": 24,
    "website manager": 26,
    "web manager": 24,
    "web lead": 22,
    "web analyst": 20,
    "web strategist": 24,
    "web": 14,
    "web producer": 24,
    "web production": 24,
    "web operations": 24,
    "web strategy": 24,
    "digital web services": 24,
    "web services": 22,
    "digital web": 22,
    "web platform": 20,
    "digital experience": 22,
    "web experience": 22,
    "web content": 21,
    "content operations": 21,
    "content systems": 21,
    "content strategist": 18,
    "content manager": 17,
    "content marketing": 16,
    "content producer": 16,
    "content lead": 16,
    "editorial": 14,
    "digital content": 17,
    "cms": 20,
    "content migration": 22,
    "web program": 20,
    "website product": 20,
    "digital strategist": 17,
    "information architecture": 20,
    "knowledge manager": 17,
    "knowledge management": 17,
    "documentation": 15,
    "communications": 12,
    "brand manager": 12,
    "digital marketing": 12,
    "growth marketing": 8,
    "talent brand": 15,
    "web marketing": 18,
    "organic growth": 14,
    "content seo": 20,
    "ai search": 22,
}

CORE_GROUPS = [
    (22, "SEO / AEO / GEO", [
        "seo", "search engine optimization", "technical seo", "organic search",
        "aeo", "answer engine optimization", "geo", "generative engine optimization",
        "llm search", "ai search", "ai overviews", "perplexity", "chatgpt"
    ]),
    (17, "CMS / web platform", [
        "sitecore", "sanity", "adobe experience manager", "aem", "contentful",
        "headless cms", "webflow", "drupal", "wordpress", "content management system"
    ]),
    (17, "web strategy / operations", [
        "web operations", "website operations", "web production", "website strategy",
        "web strategy", "digital experience", "web experience", "website roadmap"
    ]),
    (13, "content architecture / governance", [
        "content governance", "content lifecycle", "information architecture", "taxonomy",
        "structured content", "content model", "content architecture", "content standards"
    ]),
    (10, "content / editorial strategy", [
        "content strategy", "editorial strategy", "editorial", "storytelling",
        "content development", "content creation", "copywriting", "messaging",
        "campaign strategy", "content calendar", "thought leadership"
    ]),
    (10, "migration / redesign", [
        "cms migration", "site migration", "website migration", "website redesign",
        "replatform", "re-platform", "platform migration"
    ]),
    (10, "analytics / measurement", [
        "google analytics", "ga4", "search console", "ahrefs", "semrush", "conductor",
        "matomo", "piwik", "looker", "tableau", "dashboard", "web analytics"
    ]),
    (8, "UX / CRO / experimentation", [
        "user experience", "conversion rate optimization", "cro", "a/b test",
        "a/b testing", "experimentation", "test and learn", "accessibility", "wcag"
    ]),
    (8, "cross-functional roadmap", [
        "cross-functional", "stakeholder", "business requirements", "project roadmap",
        "engineering and content", "content and engineering", "product marketing"
    ]),
    (7, "B2B / SaaS / healthcare", [
        "b2b", "saas", "enterprise software", "healthcare", "life sciences", "health system"
    ]),
    (5, "marketing operations adjacency", [
        "marketo", "pardot", "salesforce", "utm", "campaign tracking", "marketing automation"
    ]),
    (7, "AI / automation", [
        "generative ai", "artificial intelligence", "llm", "large language model",
        "retrieval-augmented generation", "rag", "vector search", "natural language processing",
        "nlp", "automation"
    ]),
]

# Title families that are generally outside the bundled career profile unless the title itself
# contains a rescue term such as web/content/SEO/digital/communications.
HARD_VETO_TITLE_TERMS = [
    "accounting", "finance", "fp&a", "auditor", "audit manager", "tax manager", "business systems analyst", "systems analyst", "it support",
    "software engineer", "data engineer", "data scientist", "machine learning engineer",
    "platform engineering", "site reliability", "devops", "security engineer",
    "threat intel", "threat intelligence", "fraud manager", "sourcing manager",
    "enterprise risk management", "risk management", "erm program",
    "procurement", "construction manager", "real estate", "customer success manager",
    "renewals manager", "account executive", "sales manager", "sales director",
    "solutions architect", "field architect", "data architect", "product designer",
    "ux researcher", "people analytics", "people operations", "human resources",
    "employee relations", "pricing strategist", "deal desk", "capture manager",
    "payroll", "competitive intelligence", "analyst relations",
    "financial manager", "client manager", "escalation management", "product analyst",
    "field marketing manager", "partner marketing manager", "lifecycle marketing manager",
    "demand generation manager", "demand generation program manager",
    "product marketing manager",
]

RESCUE_TITLE_TERMS = [
    "web", "website", "content", "seo", "aeo", "geo", "search", "cms",
    "digital experience", "digital content", "communications", "brand",
    "knowledge", "documentation", "information architecture", "taxonomy"
]

# These are not automatic vetoes, but should strongly suppress a generic role
# unless web/search/content is explicit in the title.
HEAVY_ADJACENT_TERMS = [
    ("paid media", 24), ("paid social", 28), ("social advertising", 24),
    ("media buying", 24), ("programmatic advertising", 24),
    ("paid search", 20), ("demand generation", 24), ("field marketing", 18), ("product marketing manager", 18),
    ("lifecycle marketing manager", 16), ("partner marketing manager", 16),
    ("salesforce administrator", 24), ("marketo administrator", 24),
    ("hubspot administrator", 24), ("martech engineering", 24),
    ("web designer", 18), ("product designer", 22), ("visual designer", 20),
    ("e-commerce", 22), ("ecommerce", 22), ("retail media", 22),
    ("consumer packaged goods", 22), ("cpg", 22),
]


# v0.8 precision model: classify the job into a career lane before ranking it.
# v0.8.1 adds stronger explicit-title precedence for SEO specialist and digital-web roles.
# These are intentionally narrower than the general keyword lists above.
ROLE_LANES = [
    ("Web / CMS / Digital Experience",
     ["website manager", "web manager", "web producer", "web production", "web operations",
      "web strategist", "web strategy", "website strategy", "digital web services", "web services",
      "digital web", "web platform", "digital experience", "web experience",
      "website product", "web content", "cms", "content migration"],
     ["sitecore", "sanity", "adobe experience manager", "aem", "contentful", "headless cms",
      "webflow", "drupal", "wordpress", "website roadmap", "web operations", "digital experience"]),
    ("SEO / AEO / GEO",
     ["technical seo", "search engine optimization specialist", "search engine optimization",
      "seo specialist", "seo manager", "seo strategist", "search strategist", "content seo",
      "aeo", "answer engine optimization", "geo", "generative engine optimization", "ai search",
      "organic growth"],
     ["search engine optimization", "technical seo", "organic search", "aeo", "answer engine optimization",
      "generative engine optimization", "ai overviews", "search console", "ahrefs", "semrush", "conductor"]),
    ("Content Systems / Governance",
     ["content operations", "content systems", "content strategist", "content manager", "content lead",
      "information architecture", "taxonomy", "content migration", "digital content"],
     ["content governance", "content lifecycle", "information architecture", "taxonomy", "structured content",
      "content model", "content architecture", "content standards", "editorial strategy"]),
    ("Knowledge Management",
     ["knowledge manager", "knowledge management", "documentation", "knowledge base", "information architecture"],
     ["knowledge management", "knowledge base", "documentation", "taxonomy", "information architecture",
      "content governance", "self-service", "search relevance"]),
    ("Marketing Technology / Operations",
     ["marketing operations", "web marketing", "digital marketing", "marketing technology", "martech"],
     ["marketo", "pardot", "salesforce", "marketing automation", "campaign tracking", "utm", "web analytics"]),
    ("Brand / Communications",
     ["communications", "brand manager", "talent brand", "content marketing"],
     ["communications", "brand", "editorial", "storytelling", "content strategy", "website", "seo"]),
]

DIRECT_SOURCES = {
    "greenhouse", "ashby", "lever", "smartrecruiters", "workday", "icims",
    "stripe_direct", "stripe_careers"
}
AGGREGATOR_SOURCES = {"remoteok", "jobicy", "himalayas", "wwr"}

REQUIRED_HEADINGS = [
    "minimum qualifications", "required qualifications", "requirements", "what you'll need",
    "what you’ll need", "what you bring", "must have", "basic qualifications", "qualifications"
]
PREFERRED_HEADINGS = [
    "preferred qualifications", "preferred experience", "nice to have", "nice-to-have",
    "bonus points", "ideally", "preferred"
]
RESPONSIBILITY_HEADINGS = [
    "responsibilities", "what you'll do", "what you’ll do", "what you will do", "the role",
    "your impact", "what you'll be doing", "what you’ll be doing"
]

TOO_SENIOR_TERMS = ["vice president", "vp", "chief marketing officer", "chief digital officer"]

REMOTE_US_MARKERS = [
    "remote - united states", "remote, united states", "remote united states",
    "remote in united states", "remote in the us", "remote in the u.s.",
    "remote - us", "remote, us", "remote us", "us remote",
    "united states (remote)", "usa remote", "remote usa", "remote-friendly"
]
FOREIGN_MARKERS = [
    "canada", "united kingdom", "uk", "germany", "france", "australia", "singapore",
    "india", "pakistan", "poland", "ireland", "netherlands", "spain", "japan",
    "mexico", "brazil", "argentina", "colombia", "philippines", "malaysia",
    "emea", "apac", "latam"
]
US_MARKERS = ["united states", "usa", "u.s.", "us-remote", "us remote", "remote-us"]



ADJACENT_OWNERSHIP_SIGNALS = [
    "own", "ownership", "lead", "manage", "manager", "responsible", "responsibility",
    "strategy", "strategic", "campaign", "budget", "execute", "execution", "optimize",
    "optimization", "hands-on", "expertise", "proficiency", "deep knowledge",
    "experience with", "experience in", "build and scale", "develop and execute"
]

COMPANY_ALIASES = {
    "endeavorb2b": "endeavor business media",
    "zoom communications": "zoom",
    "zoom communications inc": "zoom",
    "stripe inc": "stripe",
}

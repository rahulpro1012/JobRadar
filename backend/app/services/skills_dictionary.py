"""
JobRadar Skills Dictionary
Curated list of technology skills grouped by category.
Used for both resume parsing and job description matching.
"""

SKILL_CATEGORIES = {
    "languages": [
        "java", "javascript", "typescript", "python", "c", "c++", "c#",
        "go", "golang", "rust", "kotlin", "swift", "ruby", "php", "scala",
        "perl", "r", "matlab", "dart", "lua", "groovy", "clojure",
        "haskell", "erlang", "elixir", "objective-c", "cobol", "fortran",
        "assembly", "bash", "shell", "powershell", "sql", "plsql", "tsql",
        "html", "css", "sass", "scss", "less", "xml", "json", "yaml",
        "graphql", "solidity",
    ],
    "frontend": [
        "react", "reactjs", "react.js", "angular", "angularjs", "vue",
        "vuejs", "vue.js", "svelte", "next.js", "nextjs", "nuxt",
        "nuxtjs", "gatsby", "remix", "astro", "ember", "backbone",
        "jquery", "bootstrap", "tailwind", "tailwindcss", "material ui",
        "mui", "chakra ui", "ant design", "antd", "styled-components",
        "emotion", "redux", "mobx", "zustand", "recoil", "context api",
        "webpack", "vite", "rollup", "parcel", "babel", "esbuild",
        "storybook", "figma", "sketch", "adobe xd", "responsive design",
        "pwa", "progressive web app", "web components", "shadow dom",
        "jsx", "tsx", "dom", "virtual dom", "spa", "ssr", "ssg", "csr",
        "thymeleaf", "freemarker", "handlebars", "ejs", "pug", "jinja",
        "jsp", "jstl",
    ],
    "backend": [
        "spring", "spring boot", "spring mvc", "spring data",
        "spring security", "spring cloud", "spring batch",
        "spring framework", "hibernate", "jpa", "jdbc",
        "node.js", "nodejs", "express", "express.js", "nestjs", "fastify",
        "koa", "hapi", "django", "flask", "fastapi", "tornado",
        "rails", "ruby on rails", "sinatra", "laravel", "symfony",
        "asp.net", ".net", ".net core", "entity framework",
        "gin", "echo", "fiber", "actix", "rocket",
        "servlet", "tomcat", "jetty", "undertow", "netty",
        "grpc", "rest", "rest api", "restful", "soap", "websocket",
        "microservices", "monolith", "serverless", "lambda",
        "api gateway", "oauth", "jwt", "session management",
        "middleware", "mvc", "mvvm", "clean architecture",
    ],
    "database": [
        "mysql", "postgresql", "postgres", "oracle", "sql server",
        "mssql", "sqlite", "mariadb", "mongodb", "mongoose",
        "redis", "memcached", "elasticsearch", "solr",
        "cassandra", "dynamodb", "couchdb", "couchbase",
        "neo4j", "firebase", "firestore", "supabase",
        "influxdb", "timescaledb", "cockroachdb", "planetscale",
        "prisma", "sequelize", "typeorm", "sqlalchemy",
        "knex", "drizzle", "mybatis", "jdbctemplate",
        "stored procedure", "trigger", "indexing", "query optimization",
        "database design", "normalization", "denormalization",
        "sharding", "replication", "partitioning",
    ],
    "devops": [
        "docker", "kubernetes", "k8s", "podman", "containerd",
        "aws", "amazon web services", "ec2", "s3", "rds", "lambda",
        "ecs", "eks", "fargate", "cloudformation", "cdk",
        "azure", "azure devops", "gcp", "google cloud",
        "terraform", "ansible", "puppet", "chef", "vagrant",
        "jenkins", "github actions", "gitlab ci", "circleci",
        "travis ci", "bamboo", "teamcity", "argo cd", "flux",
        "ci/cd", "ci cd", "continuous integration", "continuous deployment",
        "continuous delivery", "devops", "sre", "infrastructure as code",
        "iac", "helm", "istio", "envoy", "consul", "vault",
        "nginx", "apache", "caddy", "haproxy", "load balancer",
        "cloudflare", "cdn", "dns", "ssl", "tls",
        "linux", "ubuntu", "centos", "rhel", "debian", "unix",
        "windows server", "macos",
        "prometheus", "grafana", "datadog", "new relic", "splunk",
        "elk", "elastic", "logstash", "kibana", "fluentd",
        "monitoring", "logging", "alerting", "observability",
    ],
    "testing": [
        "junit", "junit5", "testng", "mockito", "powermock",
        "jest", "mocha", "chai", "jasmine", "cypress", "playwright",
        "selenium", "webdriver", "appium", "detox",
        "pytest", "unittest", "robot framework",
        "rspec", "minitest", "phpunit",
        "postman", "insomnia", "swagger", "openapi",
        "tdd", "bdd", "test driven development",
        "behavior driven development", "cucumber", "gherkin",
        "integration testing", "unit testing", "e2e testing",
        "end to end testing", "load testing", "performance testing",
        "stress testing", "regression testing", "smoke testing",
        "jmeter", "gatling", "locust", "k6",
        "sonarqube", "code coverage", "jacoco", "istanbul",
        "mock", "stub", "spy", "fixture",
        "mockmvc", "testcontainers",
    ],
    "version_control": [
        "git", "github", "gitlab", "bitbucket", "svn", "subversion",
        "mercurial", "git flow", "gitflow", "trunk based development",
        "branching strategy", "pull request", "merge request",
        "code review", "pair programming",
    ],
    "tools": [
        "maven", "gradle", "ant", "sbt",
        "npm", "yarn", "pnpm", "pip", "poetry", "conda",
        "intellij", "intellij idea", "eclipse", "vs code",
        "visual studio code", "visual studio", "netbeans",
        "android studio", "xcode", "sublime text", "vim", "neovim",
        "jira", "confluence", "trello", "asana", "notion",
        "slack", "teams", "zoom",
        "postman", "insomnia", "curl",
        "charles proxy", "fiddler", "wireshark",
    ],
    "concepts": [
        "data structures", "algorithms", "design patterns",
        "solid", "dry", "kiss", "yagni",
        "object oriented programming", "oop", "functional programming",
        "reactive programming", "event driven",
        "domain driven design", "ddd", "cqrs", "event sourcing",
        "agile", "scrum", "kanban", "waterfall", "safe",
        "sprint", "stand up", "retrospective",
        "system design", "high availability", "scalability",
        "fault tolerance", "disaster recovery",
        "caching", "message queue", "pub sub",
        "kafka", "rabbitmq", "activemq", "sqs", "sns",
        "distributed systems", "cap theorem", "consensus",
        "concurrency", "multithreading", "parallel programming",
        "security", "encryption", "hashing", "authentication",
        "authorization", "rbac", "sso", "saml", "oauth2",
        "rate limiting", "throttling", "circuit breaker",
        "web application", "mobile application", "desktop application",
    ],
    "data_ml": [
        "machine learning", "deep learning", "neural network",
        "tensorflow", "pytorch", "keras", "scikit-learn", "sklearn",
        "pandas", "numpy", "scipy", "matplotlib", "seaborn",
        "jupyter", "notebook", "colab",
        "nlp", "natural language processing", "computer vision",
        "llm", "large language model", "gpt", "bert", "transformer",
        "data science", "data engineering", "data pipeline",
        "etl", "data warehouse", "data lake",
        "hadoop", "spark", "hive", "pig", "flink",
        "airflow", "prefect", "dagster", "dbt",
        "tableau", "power bi", "looker", "metabase",
        "big data", "analytics", "statistics",
    ],
    "mobile": [
        "android", "ios", "react native", "flutter",
        "swiftui", "uikit", "jetpack compose",
        "kotlin multiplatform", "xamarin", "ionic", "capacitor",
        "cordova", "phonegap", "expo",
        "mobile development", "cross platform",
    ],
}

# Flatten all skills into a single set for quick lookup
ALL_SKILLS = set()
SKILL_TO_CATEGORY = {}
for category, skills in SKILL_CATEGORIES.items():
    for skill in skills:
        ALL_SKILLS.add(skill.lower())
        SKILL_TO_CATEGORY[skill.lower()] = category

# Common role titles and their variants
ROLE_TITLES = {
    "full stack developer": [
        "full stack developer", "full-stack developer", "fullstack developer",
        "full stack engineer", "full-stack engineer", "fullstack engineer",
        "full stack web developer",
    ],
    "frontend developer": [
        "frontend developer", "front-end developer", "front end developer",
        "frontend engineer", "front-end engineer", "ui developer",
        "react developer", "angular developer", "vue developer",
    ],
    "backend developer": [
        "backend developer", "back-end developer", "back end developer",
        "backend engineer", "back-end engineer", "server side developer",
        "java developer", "python developer", "node.js developer",
    ],
    "software engineer": [
        "software engineer", "software developer", "sde",
        "software development engineer", "application developer",
        "application engineer", "programmer", "coder",
    ],
    "devops engineer": [
        "devops engineer", "devops developer", "site reliability engineer",
        "sre", "platform engineer", "infrastructure engineer",
        "cloud engineer", "cloud architect",
    ],
    "data engineer": [
        "data engineer", "data developer", "etl developer",
        "big data engineer", "data platform engineer",
    ],
    "mobile developer": [
        "mobile developer", "mobile engineer", "android developer",
        "ios developer", "react native developer", "flutter developer",
    ],
    "qa engineer": [
        "qa engineer", "test engineer", "sdet",
        "quality assurance engineer", "automation engineer",
        "test automation engineer",
    ],
}

# Experience level mapping
EXPERIENCE_LEVELS = {
    (0, 1): "Junior",
    (1, 3): "Junior-Mid",
    (3, 6): "Mid",
    (6, 10): "Senior",
    (10, 99): "Lead/Principal",
}

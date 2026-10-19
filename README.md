# DNS lab stand (ОПІСМ, Topic 4)

One Docker image, one generated compose file, one container per student.

    docker build -t dnslab:latest image/
    python3 gen.py students.csv --out stand
    cd stand && docker compose up -d && cd ..
    python3 check.py --stand stand --smoke

Files:
- image/        Dockerfile, entrypoint (roles: auth, student, resolver, web), student shell helpers
- templates/    Jinja2 templates for every config, student zone and variant card
- gen.py        students.csv -> stand/ (configs, compose.yaml, cards/, instructor/)
- check.py      smoke test (--smoke) and grading of student zones
- up.sh         start + Codespaces iptables fix + smoke test

Student mode (Codespaces): python3 gen.py --student sNN --salt <salt>, then ./up.sh

Never edit files in stand/ by hand except student zones; regenerate instead.
gen.py never overwrites existing student zone files unless --force-zones.

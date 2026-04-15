# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| Latest  | :white_check_mark: |
| Previous | :x: |

## Reporting a Vulnerability

If you discover a security vulnerability in this template, please report it privately before disclosing it publicly.

### How to Report

**Preferred Method:**
- Send an email to: DuqueOrtegaMutis@gmail.com
- Use the subject line: `Security Vulnerability Report - ML-MLOps-Template`

**Alternative Methods:**
- GitHub's private vulnerability reporting: [Report Vulnerability](https://github.com/DuqueOM/ML-MLOps-Production-Template/security/advisories/new)

### What to Include

1. **Vulnerability Type** (e.g., hardcoded secrets, insecure defaults, dependency issue)
2. **Affected Templates** (specific files or patterns)
3. **Impact Assessment** (what could go wrong if the template is used as-is)
4. **Reproduction Steps** (how to trigger the vulnerability)
5. **Suggested Mitigation** (optional but helpful)

### Response Timeline

| Severity | Response Time | Description |
|----------|---------------|-------------|
| Critical | 48 hours | Hardcoded credentials, RCE in templates |
| High | 7 days | Insecure defaults that expose data |
| Medium | 14 days | Missing security best practices |
| Low | 30 days | Minor improvements |

## Security Measures in This Template

### Built-In Protections
- **Secret Scanning**: `.gitleaks.toml` + pre-commit hook for secret detection
- **Container Security**: Multi-stage Docker builds, non-root USER, HEALTHCHECK
- **Dependency Scanning**: Trivy in CI pipeline for container CVE scanning
- **Infrastructure Scanning**: tfsec + Checkov for Terraform misconfigurations
- **Code Quality**: bandit for Python security linting
- **Credential Management**: Workload Identity (GCP) and IRSA (AWS) — no hardcoded credentials

### Template Security Invariants
- **NEVER** commit secrets to tfvars or repository — use Secrets Manager
- **NEVER** hardcode API keys, tokens, or passwords in any template file
- **ALWAYS** use IAM roles (IRSA/Workload Identity) instead of static credentials
- **ALWAYS** run Trivy scan before pushing Docker images
- **ALWAYS** use `dependabot.yml` for automated dependency updates

## Security Contacts

- **Lead**: Duque Ortega Mutis
- **Email**: DuqueOrtegaMutis@gmail.com
- **GitHub**: [@DuqueOM](https://github.com/DuqueOM)

---

**Last Updated**: April 2026

# Security Policy

## Supported Versions

We currently provide security updates for the following versions:

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting Security Vulnerabilities

If you discover a security vulnerability, please **do not** report it in a public GitHub Issue.

Please report it through:

1. **GitHub Security Advisories** - Use [GitHub's security advisories feature](https://github.com/Yanyutin753/LambChat/security/advisories/new)
2. **Email** - Send detailed information to the project maintainers

When reporting, please include:

- Vulnerability type (e.g., XSS, SQL injection, CSRF, etc.)
- Steps to reproduce
- Impact scope
- Possible fix suggestions

We commit to:

- Acknowledging receipt within 48 hours
- Providing initial assessment within 7 days
- Publishing security advisories promptly after fixes are released

## Security Best Practices

When deploying LambChat, please ensure:

1. **Environment Variables** - Do not hardcode sensitive information in code
2. **HTTPS** - Production environments must use HTTPS
3. **Database** - Use strong passwords and restrict access
4. **JWT Secret** - Use a sufficiently strong random key
5. **Regular Updates** - Keep dependencies up to date

## Acknowledgments

Thank you to all contributors who report security issues!

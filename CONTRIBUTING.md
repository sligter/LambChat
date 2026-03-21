# Contributing to LambChat

Thank you for your interest in contributing to LambChat! 🎉

## 🌟 How to Contribute

### Reporting Bugs

If you find a bug, please submit a report via [GitHub Issues](https://github.com/Yanyutin753/LambChat/issues).

When submitting a bug report, please include:

1. **Clear title** - Brief description of the issue
2. **Steps to reproduce** - Detailed instructions on how to reproduce the problem
3. **Expected behavior** - What you expect to happen
4. **Actual behavior** - What actually happens
5. **Environment info** - OS, Python version, Node.js version, etc.
6. **Screenshots** - If applicable, add screenshots to help explain the issue

### Suggesting New Features

We welcome feature suggestions! Please describe in detail in an Issue:

1. Feature description
2. Use case
3. Expected effect

### Submitting Code

1. **Fork the repository**
   ```bash
   git clone https://github.com/Yanyutin753/LambChat.git
   cd LambChat
   ```

2. **Create a branch**
   ```bash
   git checkout -b feature/your-feature-name
   # or
   git checkout -b fix/your-bug-fix
   ```

3. **Install development dependencies**
   ```bash
   # Backend
   make install

   # Frontend
   cd frontend && npm install
   ```

4. **Make changes**
   - Follow the existing code style
   - Add necessary tests
   - Update relevant documentation

5. **Run tests**
   ```bash
   make test
   make lint
   ```

6. **Commit your changes**
   ```bash
   git add .
   git commit -m "feat: add new feature description"
   # or
   git commit -m "fix: fix issue description"
   ```

7. **Push and create a PR**
   ```bash
   git push origin feature/your-feature-name
   ```

## 📝 Code Standards

### Python

- Use Python 3.12+
- Follow PEP 8 guidelines
- Use `ruff` for code formatting
- Use `mypy` for type checking

### TypeScript/React

- Use TypeScript
- Follow ESLint rules
- Use functional components and Hooks

### Commit Message Convention

Follow [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation update
- `style:` Code formatting adjustment
- `refactor:` Code refactoring
- `test:` Test-related
- `chore:` Build/toolchain related

## 🔒 Security Issues

If you discover a security vulnerability, please **do not** report it in a public Issue.

Please email the security team and we will respond as soon as possible.

## 📄 License

By submitting code, you agree that your contribution will be licensed under the MIT License.

---

Thank you again for your contribution! ❤️

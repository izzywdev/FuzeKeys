# Contributing to SignMeUp

Thank you for your interest in contributing to SignMeUp! This document provides guidelines and information for contributors.

## 🚀 Getting Started

### Prerequisites
- Python 3.11+
- Node.js 18+
- Git
- GitHub account

### Development Setup

1. **Fork the repository** on GitHub
2. **Clone your fork** locally:
   ```bash
   git clone https://github.com/YOUR_USERNAME/SignMeUp.git
   cd SignMeUp
   ```

3. **Set up the development environment**:
   ```bash
   # Backend setup
   cd backend
   python -m venv venv
   source venv/bin/activate  # On Windows: .\venv\Scripts\activate
   pip install -r requirements.txt
   
   # Frontend setup
   cd ../frontend
   npm install --legacy-peer-deps
   ```

4. **Initialize the database**:
   ```bash
   cd backend
   python -c "import asyncio; from app.database import init_database; asyncio.run(init_database())"
   ```

## 🔄 Development Workflow

### 1. Create a Feature Branch
```bash
git checkout -b feature/your-feature-name
```

### 2. Make Your Changes
- Write clean, readable code
- Follow existing code style and conventions
- Add tests for new functionality
- Update documentation as needed

### 3. Test Your Changes
```bash
# Backend tests
cd backend
pytest

# Frontend tests
cd frontend
npm test
```

### 4. Commit Your Changes
```bash
git add .
git commit -m "feat: add amazing feature"
```

Follow [Conventional Commits](https://www.conventionalcommits.org/) format:
- `feat:` new feature
- `fix:` bug fix
- `docs:` documentation changes
- `style:` formatting, missing semicolons, etc.
- `refactor:` code refactoring
- `test:` adding tests
- `chore:` maintenance tasks

### 5. Push and Create Pull Request
```bash
git push origin feature/your-feature-name
```

Then create a pull request on GitHub.

## 📝 Code Style Guidelines

### Python (Backend)
- Follow PEP 8 style guide
- Use type hints where appropriate
- Use descriptive variable and function names
- Add docstrings to functions and classes
- Maximum line length: 88 characters (Black formatter)

Example:
```python
async def get_user_by_id(user_id: int, db: AsyncSession) -> Optional[User]:
    """
    Retrieve a user by their ID.
    
    Args:
        user_id: The unique identifier for the user
        db: Database session
        
    Returns:
        User object if found, None otherwise
    """
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()
```

### TypeScript/React (Frontend)
- Use TypeScript for type safety
- Follow React best practices and hooks patterns
- Use functional components
- Use descriptive component and prop names
- Follow the existing folder structure

Example:
```typescript
interface IdentityCardProps {
  identity: Identity;
  onEdit: (id: number) => void;
  onDelete: (id: number) => void;
}

const IdentityCard: React.FC<IdentityCardProps> = ({ identity, onEdit, onDelete }) => {
  return (
    <div className="bg-white rounded-lg shadow-md p-6">
      <h3 className="text-lg font-semibold">{identity.name}</h3>
      <p className="text-gray-600">{identity.description}</p>
    </div>
  );
};
```

## 🧪 Testing

### Backend Testing
- Write unit tests for new functions
- Use pytest framework
- Mock external dependencies
- Test both success and error cases

### Frontend Testing
- Write tests for components using React Testing Library
- Test user interactions and edge cases
- Mock API calls in tests

## 📚 Documentation

- Update README.md for new features
- Add inline code comments for complex logic
- Update API documentation for new endpoints
- Include examples in documentation

## 🐛 Bug Reports

When reporting bugs, please include:
- **Description**: Clear description of the issue
- **Steps to Reproduce**: Detailed steps to reproduce the bug
- **Expected Behavior**: What should happen
- **Actual Behavior**: What actually happens
- **Environment**: OS, Python version, Node.js version
- **Screenshots**: If applicable

## 💡 Feature Requests

For feature requests, please include:
- **Problem**: What problem does this solve?
- **Solution**: Proposed solution or feature
- **Use Case**: How would this be used?
- **Alternatives**: Any alternative solutions considered

## 🚫 Code of Conduct

- Be respectful and inclusive
- Welcome newcomers and help them learn
- Focus on what is best for the community
- Show empathy towards other community members

## 📞 Getting Help

- Check existing issues and documentation first
- Create a GitHub issue for bugs or feature requests
- Join discussions in GitHub Discussions
- Tag maintainers for urgent issues

## 🎯 Priority Areas

We especially welcome contributions in these areas:
- **Automation Scripts**: New website signup automations
- **Security**: Enhanced encryption and security features
- **UI/UX**: Improved user interface and experience
- **Testing**: Additional test coverage
- **Documentation**: Better docs and examples
- **Performance**: Optimization and efficiency improvements

## 🏆 Recognition

Contributors will be recognized in:
- GitHub contributors list
- Release notes for significant contributions
- Special thanks in documentation

Thank you for contributing to SignMeUp! 🚀 
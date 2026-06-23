# FuzeKeys 🚀

**Intelligent Identity & Account Management System**

FuzeKeys is a sophisticated automation platform that intelligently manages multiple digital identities and automates account creation across various websites. Built with modern technologies, it features encrypted data storage, AI-powered automation scripts, and a beautiful React frontend.

## ✨ Features

### 🔐 **Secure Identity Management**
- **Multiple Digital Identities**: Create and manage separate identities for different use cases (professional, personal, etc.)
- **Encrypted Storage**: All sensitive data is encrypted using industry-standard encryption
- **Master Key Protection**: User-controlled encryption keys for maximum security

### 🤖 **Intelligent Automation**
- **Smart Signup Scripts**: AI-powered automation that adapts to different website forms
- **CAPTCHA Handling**: Advanced CAPTCHA detection and solving capabilities
- **Email Verification**: Automated email verification workflows
- **Form Analysis**: Intelligent form field detection and completion

### 💬 **AI Assistant**
- **Chat Interface**: Natural language interaction for account management
- **Contextual Responses**: AI understands your automation needs and provides relevant suggestions
- **Guided Workflows**: Step-by-step assistance for complex tasks

### 📊 **Comprehensive Dashboard**
- **Account Overview**: Real-time status of all your accounts across platforms
- **Success Metrics**: Track automation success rates and performance
- **Activity Logs**: Detailed logging of all automation activities

## 🏗️ Architecture

### Backend (Python/FastAPI)
- **FastAPI Framework**: High-performance async API
- **SQLAlchemy ORM**: Async database operations with SQLite/PostgreSQL support
- **Playwright Integration**: Web automation and browser control
- **OpenAI Integration**: AI-powered chat assistant and form analysis
- **Cryptography**: Advanced encryption for sensitive data

### Frontend (React/TypeScript)
- **React 18**: Modern React with hooks and context
- **TypeScript**: Type-safe development
- **Tailwind CSS**: Utility-first styling framework
- **React Router**: Client-side routing
- **Responsive Design**: Works on desktop and mobile

### Database
- **SQLite**: Local development and small deployments
- **PostgreSQL**: Production-ready scalable storage
- **Encrypted Fields**: Sensitive data is encrypted at the field level
- **Async Operations**: Non-blocking database operations

## 🚀 Quick Start

### Prerequisites
- **Python 3.11+**
- **Node.js 18+**
- **Git**

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/FuzeKeys.git
   cd FuzeKeys
   ```

2. **Backend Setup**
   ```bash
   cd backend
   python -m venv venv
   
   # Windows
   .\venv\Scripts\activate
   
   # macOS/Linux
   source venv/bin/activate
   
   pip install -r requirements.txt
   ```

3. **Frontend Setup**
   ```bash
   cd frontend
   npm install --legacy-peer-deps
   ```

4. **Initialize Database**
   ```bash
   cd backend
   python -c "import asyncio; from app.database import init_database; asyncio.run(init_database())"
   ```

### Running the Application

1. **Start Backend Server**
   ```bash
   cd backend
   python working_server.py
   ```
   Backend will be available at: `http://localhost:8002`

2. **Start Frontend (in a new terminal)**
   ```bash
   cd frontend
   npm start
   ```
   Frontend will be available at: `http://localhost:3000`

## 📁 Project Structure

```
FuzeKeys/
├── backend/                 # Python FastAPI backend
│   ├── app/
│   │   ├── models/         # SQLAlchemy database models
│   │   ├── routers/        # API route handlers
│   │   ├── utils/          # Utility functions (encryption, logging)
│   │   ├── database.py     # Database configuration
│   │   └── main.py         # FastAPI application
│   ├── data/               # SQLite database files
│   ├── requirements.txt    # Python dependencies
│   └── working_server.py   # Standalone server script
├── frontend/               # React TypeScript frontend
│   ├── src/
│   │   ├── components/     # React components
│   │   ├── pages/          # Page components
│   │   ├── services/       # API services
│   │   ├── context/        # React contexts
│   │   └── types/          # TypeScript type definitions
│   ├── public/             # Static assets
│   └── package.json        # Node.js dependencies
└── docker-compose.yml      # Docker configuration
```

## 🔧 Configuration

### Environment Variables

Create a `.env` file in the backend directory:

```env
# Database
DATABASE_URL_ASYNC=postgresql+asyncpg://username:password@localhost/fuzekeys

# Security
MASTER_KEY_SALT=your_secure_salt_here
SECRET_KEY=your_secret_key_here

# OpenAI (optional)
OPENAI_API_KEY=your_openai_api_key

# Application
DEBUG=True
HOST=localhost
PORT=8002
```

## 🛡️ Security Features

- **End-to-End Encryption**: All sensitive data is encrypted before storage
- **Master Key Control**: Users control their own encryption keys
- **Secure Authentication**: JWT-based authentication with bcrypt password hashing
- **SQL Injection Protection**: Parameterized queries and ORM protection
- **CORS Configuration**: Properly configured cross-origin resource sharing

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🚧 Development Status

**Current Version**: 1.0.0 (Semantic Versioning)

## 🔧 FuzeInfra Integration

FuzeKeys now integrates with the shared FuzeInfra platform for infrastructure services:

- **Shared Database**: Uses FuzeInfra PostgreSQL, MongoDB, Redis
- **Monitoring**: Grafana, Prometheus integration
- **Message Queues**: Kafka and RabbitMQ support
- **Logging**: Centralized logging with Loki

### Starting with FuzeInfra

1. **Start FuzeInfra services first**:
   ```bash
   cd modules/FuzeInfra
   ./infra-up.sh  # or infra-up.bat on Windows
   ```

2. **Start FuzeKeys application**:
   ```bash
   docker-compose up -d
   ```

## 🔧 Site Integrations

FuzeKeys includes a comprehensive site integration system located in `backend/app/integrations/site/` that provides automated account management for various platforms.

### Architecture
```
backend/app/integrations/site/
├── __init__.py                 # Integration discovery and management
├── permit_io/                  # Permit.io integration
│   ├── __init__.py            # Main integration class
│   ├── models.py              # Data models
│   ├── config.py              # Site configuration
│   ├── signup.py              # Account creation automation
│   ├── signin.py              # Authentication automation
│   └── apikey.py              # API key creation automation
└── [other_sites]/             # Future site integrations
```

### Supported Sites

#### Permit.io
- ✅ **Signup**: Automated account creation with form detection
- ✅ **Signin**: Authentication with session management  
- ✅ **API Key Creation**: Automated API key generation
- ✅ **Headless Browser**: Playwright-powered with screenshot debugging
- ✅ **Error Handling**: Comprehensive error detection and reporting

### API Usage
```bash
# Create account
curl -X POST "http://localhost:8002/api/v1/integrations/signup" \
  -H "Content-Type: application/json" \
  -d '{
    "site": "permit.io",
    "email": "user@example.com", 
    "password": "secure_password",
    "first_name": "John",
    "last_name": "Doe"
  }'

# Sign in
curl -X POST "http://localhost:8002/api/v1/integrations/signin" \
  -H "Content-Type: application/json" \
  -d '{
    "site": "permit.io",
    "email": "user@example.com",
    "password": "secure_password"
  }'

# Create API key
curl -X POST "http://localhost:8002/api/v1/integrations/apikey" \
  -H "Content-Type: application/json" \
  -d '{
    "site": "permit.io",
    "email": "user@example.com",
    "password": "secure_password", 
    "key_name": "FuzeKeys"
  }'
```

### Direct Integration Usage
```python
from app.integrations.site.permit_io import PermitIOIntegration
from app.integrations.site.permit_io.models import PermitIOCredentials

credentials = PermitIOCredentials(
    email="user@example.com",
    password="secure_password",
    first_name="John",
    last_name="Doe"
)

integration = PermitIOIntegration(headless=True)

# Create account
result = await integration.signup_account(credentials)
print(f"Signup result: {result.success}")

# Sign in
result = await integration.signin_account("user@example.com", "password")
print(f"Signin result: {result.success}")

# Create API key
result = await integration.create_api_key("user@example.com", "password", "MyKey")
print(f"API key: {result.data['key_value']}")
```

## 🧪 Testing & CI/CD

FuzeKeys includes comprehensive testing and continuous integration:

### Running Tests

```bash
# Backend tests
cd backend
pytest tests/ -v --cov=app

# Frontend tests  
cd frontend
npm test -- --coverage
```

### GitHub Actions CI/CD

- **Automated Testing**: Python and Node.js tests on multiple versions
- **Code Quality**: Linting with Flake8, ESLint, Black, isort
- **Security Scanning**: Bandit, Safety, npm audit
- **Type Checking**: MyPy for Python, TypeScript for frontend
- **Coverage Reports**: Codecov integration

### Submodules

The project includes git submodules for shared infrastructure:

- **EnvManager**: Environment management utilities
- **FuzeInfra**: Shared infrastructure platform  
- **FuzeFront**: Frontend components and utilities

```bash
# Initialize submodules
git submodule update --init --recursive
```

### ✅ Completed Features
- Identity management with encryption
- Account tracking and status monitoring
- Basic automation framework
- React frontend with responsive design
- SQLite database with async operations
- AI chat assistant
- Comprehensive API documentation

### 🔄 In Progress
- Advanced automation scripts
- Email verification automation
- CAPTCHA solving integration
- Enhanced AI capabilities

### 📋 Planned Features
- Browser extension
- Mobile application
- Advanced analytics
- Team collaboration features
- Enterprise authentication (SSO)

## 🐛 Known Issues

- Browser automation requires Playwright browser installation
- Some websites have advanced bot detection
- Email verification depends on email provider APIs

## 📞 Support

For questions and support:
- Create an issue on GitHub
- Check the documentation
- Review existing issues and discussions

## 🙏 Acknowledgments

- **FastAPI** - For the amazing async web framework
- **React** - For the powerful frontend library
- **Playwright** - For reliable web automation
- **SQLAlchemy** - For excellent ORM capabilities
- **Tailwind CSS** - For beautiful, responsive styling

---

**Built with ❤️ for automating the tedious parts of the web** 
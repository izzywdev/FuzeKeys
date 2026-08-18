from sqlalchemy import JSON, Boolean, Column, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class SignupScript(Base):
    """SignupScript model for storing automation scripts."""

    __tablename__ = "signup_scripts"

    id = Column(Integer, primary_key=True, index=True)

    # Website information
    website_name = Column(String(200), nullable=False)
    website_url = Column(String(500), nullable=False)
    website_domain = Column(String(200), index=True, nullable=False)

    # Script metadata
    version = Column(String(20), default="1.0.0")
    is_active = Column(Boolean, default=True)
    success_rate = Column(Float, default=0.0)  # Success rate percentage

    # Script content
    script_type = Column(String(50), default="playwright")  # playwright, selenium, etc.
    script_content = Column(Text, nullable=False)  # The actual automation script

    # Form analysis
    form_selectors = Column(JSON)  # CSS selectors for form fields
    required_fields = Column(JSON)  # List of required fields
    optional_fields = Column(JSON)  # List of optional fields
    captcha_present = Column(Boolean, default=False)
    email_verification_required = Column(Boolean, default=False)

    # Automation settings
    wait_times = Column(JSON)  # Custom wait times for different steps
    retry_settings = Column(JSON)  # Retry configuration
    browser_settings = Column(JSON)  # Browser configuration

    # Learning data
    learning_data = Column(JSON)  # Data collected during script learning
    common_errors = Column(JSON)  # Common errors and solutions

    # Usage statistics
    usage_count = Column(Integer, default=0)
    successful_runs = Column(Integer, default=0)
    failed_runs = Column(Integer, default=0)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_used = Column(DateTime(timezone=True))
    last_successful_run = Column(DateTime(timezone=True))

    # Relationships
    accounts = relationship("Account", back_populates="signup_script")

    def __repr__(self):
        return f"<SignupScript(id={self.id}, website='{self.website_name}', version='{self.version}')>"

    def update_success_rate(self):
        """Update the success rate based on usage statistics."""
        total_runs = self.successful_runs + self.failed_runs
        if total_runs > 0:
            self.success_rate = (self.successful_runs / total_runs) * 100
        else:
            self.success_rate = 0.0

"""Add site automation methods

Revision ID: d3020ha03e0h
Revises: c2019ga02d9g
Create Date: 2025-01-13 15:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'd3020ha03e0h'
down_revision = 'c2019ga02d9g'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create the sites table if it doesn't exist
    op.create_table('sites',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('display_name', sa.String(length=150), nullable=False),
        sa.Column('url', sa.String(length=500), nullable=False),
        sa.Column('logo_url', sa.String(length=500), nullable=True),
        sa.Column('category', sa.String(length=50), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        
        # Difficulty levels
        sa.Column('signup_difficulty', 
                 sa.Enum('EASY', 'MEDIUM', 'HARD', 'EXTREME', name='difficultylevel'), 
                 nullable=True),
        sa.Column('signin_difficulty', 
                 sa.Enum('EASY', 'MEDIUM', 'HARD', 'EXTREME', name='difficultylevel'), 
                 nullable=True),
        sa.Column('apikey_difficulty', 
                 sa.Enum('EASY', 'MEDIUM', 'HARD', 'EXTREME', name='difficultylevel'), 
                 nullable=True),
        
        # NEW: Method availability tracking (JSON arrays)
        sa.Column('signup_methods', sa.JSON(), nullable=True),
        sa.Column('signin_methods', sa.JSON(), nullable=True),
        sa.Column('apikey_methods', sa.JSON(), nullable=True),
        
        # NEW: Preferred method order
        sa.Column('signup_preferred_method', 
                 sa.Enum('API', 'SCRAPING', 'MANUAL', 'HYBRID', name='automationmethod'), 
                 nullable=True),
        sa.Column('signin_preferred_method', 
                 sa.Enum('API', 'SCRAPING', 'MANUAL', 'HYBRID', name='automationmethod'), 
                 nullable=True),
        sa.Column('apikey_preferred_method', 
                 sa.Enum('API', 'SCRAPING', 'MANUAL', 'HYBRID', name='automationmethod'), 
                 nullable=True),
        
        # NEW: Automation technology requirements
        sa.Column('automation_framework', 
                 sa.Enum('SELENIUM', 'PLAYWRIGHT', 'REQUESTS', 'PUPPETEER', 'API_ONLY', 
                        name='automationframework'), 
                 nullable=True),
        sa.Column('requires_javascript', sa.Boolean(), nullable=True),
        sa.Column('requires_browser_automation', sa.Boolean(), nullable=True),
        sa.Column('requires_proxy', sa.Boolean(), nullable=True),
        sa.Column('requires_user_agent_rotation', sa.Boolean(), nullable=True),
        
        # NEW: API method details
        sa.Column('api_signup_endpoint', sa.String(length=500), nullable=True),
        sa.Column('api_signin_endpoint', sa.String(length=500), nullable=True),
        sa.Column('api_key_endpoint', sa.String(length=500), nullable=True),
        sa.Column('api_authentication_method', sa.String(length=50), nullable=True),
        sa.Column('api_base_url', sa.String(length=500), nullable=True),
        
        # Verification requirements
        sa.Column('requires_email_verification', sa.Boolean(), nullable=True),
        sa.Column('requires_phone_verification', sa.Boolean(), nullable=True),
        sa.Column('requires_sms_verification', sa.Boolean(), nullable=True),
        sa.Column('requires_authenticator', sa.Boolean(), nullable=True),
        sa.Column('has_captcha', sa.Boolean(), nullable=True),
        sa.Column('captcha_type', sa.String(length=50), nullable=True),
        
        # Anti-scraping measures
        sa.Column('anti_bot_techniques', sa.JSON(), nullable=True),
        
        # Implementation status
        sa.Column('signup_status', 
                 sa.Enum('NOT_STARTED', 'IN_PROGRESS', 'COMPLETED', 'FAILED', 'BLOCKED', 
                        name='implementationstatus'), 
                 nullable=True),
        sa.Column('signin_status', 
                 sa.Enum('NOT_STARTED', 'IN_PROGRESS', 'COMPLETED', 'FAILED', 'BLOCKED', 
                        name='implementationstatus'), 
                 nullable=True),
        sa.Column('apikey_status', 
                 sa.Enum('NOT_STARTED', 'IN_PROGRESS', 'COMPLETED', 'FAILED', 'BLOCKED', 
                        name='implementationstatus'), 
                 nullable=True),
        
        # Additional metadata
        sa.Column('priority', sa.Integer(), nullable=True),
        sa.Column('estimated_hours', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        
        # Legacy API information
        sa.Column('has_official_api', sa.Boolean(), nullable=True),
        sa.Column('api_documentation_url', sa.String(length=500), nullable=True),
        sa.Column('api_rate_limits', sa.String(length=200), nullable=True),
        
        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_tested', sa.DateTime(timezone=True), nullable=True),
        
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes
    op.create_index(op.f('ix_sites_id'), 'sites', ['id'], unique=False)
    op.create_index(op.f('ix_sites_name'), 'sites', ['name'], unique=False)
    op.create_index(op.f('ix_sites_category'), 'sites', ['category'], unique=False)


def downgrade() -> None:
    # Drop the sites table and all related enums
    op.drop_index(op.f('ix_sites_category'), table_name='sites')
    op.drop_index(op.f('ix_sites_name'), table_name='sites')
    op.drop_index(op.f('ix_sites_id'), table_name='sites')
    op.drop_table('sites')
    
    # Drop the enums
    sa.Enum(name='automationframework').drop(op.get_bind())
    sa.Enum(name='automationmethod').drop(op.get_bind())
    sa.Enum(name='implementationstatus').drop(op.get_bind())
    sa.Enum(name='difficultylevel').drop(op.get_bind()) 
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import openai
import os
import json
import re
from datetime import datetime

from app.database import get_db
from app.models.user import User
from app.models.identity import Identity
from app.routers.auth import get_current_user
from app.automation.web_scraper import analyze_website_signup
from app.utils.logging import get_logger, log_automation_event

logger = get_logger(__name__)
router = APIRouter()

# OpenAI Configuration
openai.api_key = os.getenv("OPENAI_API_KEY")


class ChatMessage(BaseModel):
    message: str


class ChatResponse(BaseModel):
    response: str
    action_type: Optional[str] = None
    suggested_actions: List[str] = []
    automation_status: Optional[str] = None


class SignupRequest(BaseModel):
    website_url: str
    identity_id: int
    additional_instructions: Optional[str] = None


def parse_signup_request(message: str) -> Optional[Dict[str, Any]]:
    """Parse natural language signup request."""
    # Simple regex patterns for common requests
    patterns = [
        r"sign me up for\s+(.+?)(?:\s+with\s+(.+?))?(?:\s+identity)?",
        r"create an account on\s+(.+?)(?:\s+using\s+(.+?))?",
        r"register me on\s+(.+?)(?:\s+with\s+(.+?))?",
    ]
    
    message_lower = message.lower()
    
    for pattern in patterns:
        match = re.search(pattern, message_lower)
        if match:
            website = match.group(1).strip()
            identity_name = match.group(2).strip() if match.group(2) else None
            
            # Try to extract URL if it looks like one
            url_match = re.search(r'https?://[^\s]+', website)
            if url_match:
                website_url = url_match.group(0)
            else:
                # Try to construct URL
                website_clean = re.sub(r'[^\w\.]', '', website)
                if '.' not in website_clean:
                    website_url = f"https://{website_clean}.com"
                else:
                    website_url = f"https://{website_clean}"
            
            return {
                "website_url": website_url,
                "identity_name": identity_name,
                "original_request": message
            }
    
    return None


async def get_ai_response(message: str, context: Dict[str, Any] = None) -> str:
    """Get AI response for chat message."""
    try:
        system_prompt = """
        You are an AI assistant for FuzeKeys, a system that manages digital identities and automates account creation.
        
        You can help users with:
        1. Creating and managing digital identities
        2. Automating account signup processes
        3. Managing account credentials and API keys
        4. Providing guidance on automation features
        
        When users request account creation, parse their request and provide clear next steps.
        Be helpful, security-conscious, and explain what the system can do.
        """
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message}
        ]
        
        if context:
            context_message = f"User context: {json.dumps(context, indent=2)}"
            messages.insert(1, {"role": "system", "content": context_message})
        
        response = await openai.ChatCompletion.acreate(
            model=os.getenv("OPENAI_MODEL", "gpt-4"),
            messages=messages,
            max_tokens=500,
            temperature=0.7
        )
        
        return response.choices[0].message.content.strip()
        
    except Exception as e:
        logger.error(f"Error getting AI response: {str(e)}")
        return "I'm sorry, I'm having trouble processing your request right now. Please try again later."


@router.post("/message", response_model=ChatResponse)
async def chat_message(
    chat_data: ChatMessage,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Process chat message and return response."""
    try:
        message = chat_data.message.strip()
        
        # Check if this is a signup request
        signup_request = parse_signup_request(message)
        
        if signup_request:
            # Handle signup request
            return await handle_signup_request(signup_request, current_user, db)
        
        # Handle general chat
        context = {
            "user_id": current_user.id,
            "username": current_user.username,
            "has_identities": len(current_user.identities) > 0 if current_user.identities else False
        }
        
        ai_response = await get_ai_response(message, context)
        
        # Generate suggested actions based on message content
        suggested_actions = generate_suggested_actions(message, current_user)
        
        return ChatResponse(
            response=ai_response,
            suggested_actions=suggested_actions
        )
        
    except Exception as e:
        logger.error(f"Error processing chat message: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error processing your message"
        )


async def handle_signup_request(
    signup_request: Dict[str, Any],
    current_user: User,
    db: AsyncSession
) -> ChatResponse:
    """Handle automated signup request."""
    try:
        website_url = signup_request["website_url"]
        identity_name = signup_request.get("identity_name")
        
        # Find appropriate identity
        identity = None
        if identity_name:
            # Find identity by name
            for user_identity in current_user.identities:
                if identity_name.lower() in user_identity.name.lower():
                    identity = user_identity
                    break
        
        if not identity and current_user.identities:
            # Use first available identity
            identity = current_user.identities[0]
        
        if not identity:
            return ChatResponse(
                response="I'd love to help you sign up, but you don't have any identities set up yet. "
                        "Please create an identity first, then I can help you with automated signups.",
                action_type="create_identity",
                suggested_actions=["Create your first identity", "Learn about identities"]
            )
        
        # Analyze the website
        try:
            log_automation_event("signup_analysis_start", {"website": website_url}, website_url)
            
            # This would typically analyze the website and create a signup script
            # For now, we'll return a response indicating the process is starting
            
            response = f"""
            Great! I'll help you sign up for {website_url} using your "{identity.name}" identity.
            
            Here's what I'm going to do:
            1. Analyze the signup process for {website_url}
            2. Create an automated signup script
            3. Fill out the form using your identity information
            4. Store the account details securely
            
            This may take a few minutes. I'll update you on the progress.
            """
            
            return ChatResponse(
                response=response,
                action_type="automated_signup",
                automation_status="analyzing",
                suggested_actions=[
                    f"View {identity.name} identity details",
                    "Cancel signup process",
                    "Choose different identity"
                ]
            )
            
        except Exception as e:
            logger.error(f"Error analyzing website {website_url}: {str(e)}")
            return ChatResponse(
                response=f"I encountered an issue analyzing {website_url}. "
                        f"This could be due to the website's structure or security measures. "
                        f"Would you like me to try a different approach or would you prefer to sign up manually?",
                suggested_actions=[
                    "Try manual signup guidance",
                    "Report website issue",
                    "Choose different website"
                ]
            )
        
    except Exception as e:
        logger.error(f"Error handling signup request: {str(e)}")
        return ChatResponse(
            response="I encountered an error processing your signup request. Please try again.",
            suggested_actions=["Try again", "Contact support"]
        )


def generate_suggested_actions(message: str, user: User) -> List[str]:
    """Generate suggested actions based on message content."""
    suggestions = []
    message_lower = message.lower()
    
    # Common action suggestions
    if any(word in message_lower for word in ['identity', 'identities', 'profile']):
        suggestions.extend(["View your identities", "Create new identity"])
    
    if any(word in message_lower for word in ['account', 'accounts', 'signup', 'sign up']):
        suggestions.extend(["View your accounts", "Start automated signup"])
    
    if any(word in message_lower for word in ['api', 'key', 'token']):
        suggestions.extend(["View API keys", "Generate new API key"])
    
    if any(word in message_lower for word in ['help', 'how', 'what']):
        suggestions.extend(["View documentation", "See example commands"])
    
    # Limit to 4 suggestions
    return suggestions[:4]


@router.post("/signup", response_model=ChatResponse)
async def initiate_signup(
    signup_data: SignupRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Initiate automated signup process."""
    try:
        # Find the identity
        identity_result = await db.execute(
            select(Identity).where(
                (Identity.id == signup_data.identity_id) & 
                (Identity.user_id == current_user.id)
            )
        )
        identity = identity_result.scalar_one_or_none()
        
        if not identity:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Identity not found"
            )
        
        # Start the signup process
        log_automation_event("manual_signup_start", {
            "website": signup_data.website_url,
            "identity": identity.name
        }, signup_data.website_url)
        
        response = f"Starting automated signup for {signup_data.website_url} using {identity.name} identity..."
        
        return ChatResponse(
            response=response,
            action_type="automated_signup",
            automation_status="starting"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error initiating signup: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error starting signup process"
        ) 
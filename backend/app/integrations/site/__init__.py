"""
Site Integrations Package

This package contains site-specific integrations for automated account management.
Each site integration should provide the following standardized modules:

- signup.py: Account creation automation
- signin.py: Authentication automation
- apikey.py: API key creation and management
- models.py: Data models for the site
- config.py: Site-specific configuration
"""

from typing import Dict, List, Any
import importlib
import pkgutil

def get_available_sites() -> List[str]:
    """Get a list of all available site integrations."""
    sites = []
    for importer, modname, ispkg in pkgutil.iter_modules(__path__):
        if ispkg:
            sites.append(modname)
    return sites

def get_site_integration(site_name: str) -> Any:
    """
    Dynamically import and return a site integration module.
    
    Args:
        site_name: Name of the site integration to load
        
    Returns:
        The imported site integration module
        
    Raises:
        ImportError: If the site integration is not found
    """
    try:
        return importlib.import_module(f"app.integrations.site.{site_name}")
    except ImportError:
        raise ImportError(f"Site integration '{site_name}' not found")

def get_site_capabilities(site_name: str) -> Dict[str, bool]:
    """
    Get the capabilities of a specific site integration.
    
    Args:
        site_name: Name of the site integration
        
    Returns:
        Dictionary indicating which capabilities are available
    """
    try:
        site_module = get_site_integration(site_name)
        capabilities = {
            'signup': hasattr(site_module, 'signup') or hasattr(site_module, 'SignupAutomation'),
            'signin': hasattr(site_module, 'signin') or hasattr(site_module, 'SigninAutomation'),
            'apikey': hasattr(site_module, 'apikey') or hasattr(site_module, 'ApiKeyAutomation'),
        }
        return capabilities
    except ImportError:
        return {'signup': False, 'signin': False, 'apikey': False} 
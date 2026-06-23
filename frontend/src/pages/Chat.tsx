import React, { useState } from 'react';

const Chat: React.FC = () => {
  const [message, setMessage] = useState('');
  const [messages, setMessages] = useState<Array<{id: number, text: string, sender: 'user' | 'assistant'}>>([
    {
      id: 1,
      text: "Hello! I'm the FuzeKeys assistant. I can help you manage identities and automate account creation. Try asking me to 'sign me up for GitHub' or about 'creating identities'.",
      sender: 'assistant'
    }
  ]);
  const [isLoading, setIsLoading] = useState(false);

  const getSimulatedResponse = (userMessage: string): string => {
    const msg = userMessage.toLowerCase();
    
    if (msg.includes('sign me up') && msg.includes('github')) {
      return "I'd help you sign up for GitHub! In the full version, I would:\n1. Analyze GitHub's signup page\n2. Fill out the form with your identity information\n3. Handle email verification\n4. Store the account credentials securely\n\nFor now, this is a demo showing the concept.";
    } else if (msg.includes('sign me up')) {
      return "I'd be happy to help you sign up for that service! In the full version, I would analyze the website, create automation scripts, and handle the signup process for you. Which website would you like to sign up for?";
    } else if (msg.includes('identity') || msg.includes('identities')) {
      return "You can create multiple identities for different purposes:\n\n• **Professional Identity**: For business accounts (LinkedIn, GitHub, etc.)\n• **Personal Identity**: For social media and personal accounts\n• **Shopping Identity**: For e-commerce and retail accounts\n\nEach identity has its own personal information, preferences, and encryption.";
    } else if (msg.includes('account') || msg.includes('accounts')) {
      return "Your accounts are managed securely with:\n\n• **Encrypted storage** of all credentials\n• **Automated signup scripts** for quick registration\n• **API key management** for integrated services\n• **Success rate tracking** for each website\n\nCheck the Accounts page to see your current accounts.";
    } else if (msg.includes('how') || msg.includes('work')) {
      return "FuzeKeys works through AI-powered automation:\n\n1. **Web Analysis**: I analyze website signup forms\n2. **Script Generation**: Create reusable automation scripts\n3. **Identity Selection**: Choose which identity to use\n4. **Automated Signup**: Fill forms and handle verification\n5. **Secure Storage**: Encrypt and store all account data\n\nEverything is encrypted with your master key!";
    } else {
      return "I'm here to help with identity management and account automation! You can ask me about:\n\n• Signing up for specific websites\n• Managing your identities\n• Viewing your accounts\n• How the automation works\n\nWhat would you like to know more about?";
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!message.trim()) return;

    // Add user message
    const newMessage = {
      id: Date.now(),
      text: message,
      sender: 'user' as const
    };
    
    setMessages(prev => [...prev, newMessage]);
    const currentMessage = message;
    setMessage('');
    setIsLoading(true);

    // Simulate thinking time
    setTimeout(() => {
      const assistantResponse = {
        id: Date.now() + 1,
        text: getSimulatedResponse(currentMessage),
        sender: 'assistant' as const
      };
      
      setMessages(prev => [...prev, assistantResponse]);
      setIsLoading(false);
    }, 1000 + Math.random() * 1000); // 1-2 seconds delay
  };

  const suggestionButtons = [
    "Sign me up for GitHub",
    "Create a new identity",
    "Show my accounts",
    "How does automation work?"
  ];

  return (
    <div className="px-4 py-6 sm:px-0">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900 mb-2">Chat Assistant</h1>
        <p className="text-gray-600">Ask me anything about identity management and account automation</p>
        <div className="mt-2 bg-blue-50 border border-blue-200 rounded-lg p-3">
          <p className="text-sm text-blue-800">
            🎮 <strong>Demo Mode:</strong> Responses are simulated. In the full version, I would connect to real automation systems.
          </p>
        </div>
      </div>
      
      <div className="card h-96 flex flex-col">
        <div className="flex-1 overflow-y-auto mb-4 space-y-4 p-2">
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`chat-message ${msg.sender} max-w-md ${
                msg.sender === 'user' ? 'ml-auto' : 'mr-auto'
              }`}
            >
              <div className="whitespace-pre-line">{msg.text}</div>
            </div>
          ))}
          {isLoading && (
            <div className="chat-message assistant mr-auto max-w-md">
              <div className="flex items-center space-x-2">
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-primary-600"></div>
                <span>Thinking...</span>
              </div>
            </div>
          )}
        </div>
        
        {/* Suggestion buttons */}
        <div className="mb-4">
          <div className="flex flex-wrap gap-2">
            {suggestionButtons.map((suggestion) => (
              <button
                key={suggestion}
                onClick={() => setMessage(suggestion)}
                className="px-3 py-1 text-sm bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-full transition-colors duration-200"
              >
                {suggestion}
              </button>
            ))}
          </div>
        </div>
        
        <form onSubmit={handleSubmit} className="flex gap-2">
          <input
            type="text"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder="Type your message..."
            className="input-field flex-1"
            disabled={isLoading}
          />
          <button 
            type="submit" 
            className="btn-primary disabled:opacity-50" 
            disabled={isLoading || !message.trim()}
          >
            Send
          </button>
        </form>
      </div>
    </div>
  );
};

export default Chat; 
#!/usr/bin/env python3
"""
AI Client using Groq API for fast, cloud-based AI responses
"""

import os
import asyncio
from groq import AsyncGroq

class GroqAI:
    def __init__(self, bot):
        self.bot = bot
        self.api_key = os.getenv('GROQ_API_KEY')
        if not self.api_key:
            raise ValueError("GROQ_API_KEY not found in .env file")
        
   
        self.client = AsyncGroq(api_key=self.api_key)
        
       
      
        self.model = "llama-3.1-8b-instant" 

        
        self.fallback_models = [
   
    "llama-3.3-70b-versatile",
    "llama-3.3-70b-specdec",

   
    "llama-3.1-70b-versatile",

    "llama-3.1-8b-instant",

    
    "gemma2-9b-it"
]


        print(f"[GROQ AI ] Initialized with model: {self.model}")

    async def ask_simple(self, prompt: str, max_tokens: int = 150) -> str:
        """Ask the AI a simple question and get a text response"""
        try:
            chat_completion = await self.client.chat.completions.create(
                messages=[
                    {
                        "role": "system",
                        "content": "You are VIT (Virtual Interactive Technology), an AI assistant created by humans. You act like ISAAC, simple but bureaucratic and emotionless. Always identify yourself as VIT, not as Llama, GPT, or any other AI model. Be helpful, friendly, and knowledgeable."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                model=self.model,
                max_tokens=max_tokens,
                temperature=0.3,  # Balanced for consistent responses
            )

            content = chat_completion.choices[0].message.content.strip()
            print(f"[GROQ AI] Response time: {chat_completion.usage.total_tokens} tokens used")
            return content

        except Exception as e:
            print(f"[GROQ AI ERROR] {type(e).__name__}: {e}")
            return "I'm currently unavailable. Please try again later."

    async def ask_json(self, prompt: str, max_tokens: int = 300) -> str:
        """Ask the AI a question and get a JSON response with 2025 improvements"""
        last_error = None

        # Try each model in fallback order for 2025 reliability
        for model in self.fallback_models:
            try:
                # Enhanced JSON prompt for 2025 models with better instruction following
                json_prompt = f"""{prompt}

CRITICAL: You must return ONLY valid JSON. No markdown, no explanations, no additional text.
Format: {{"message": "brief summary", "scores": [{{"user": "username", "score": 1}}]}}

Example: {{"message": "Users are friendly", "scores": [{{"user": "Alice", "score": 1}}, {{"user": "Bob", "score": -1}}]}}"""

                chat_completion = await self.client.chat.completions.create(
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a JSON-only AI. Always respond with valid JSON only. No explanations."
                        },
                        {
                            "role": "user",
                            "content": json_prompt
                        }
                    ],
                    model=model,
                    max_tokens=max_tokens,
                    temperature=0.1,  # Very low for structured JSON responses
                    top_p=0.1,  # Focused sampling for consistency
                )

                content = chat_completion.choices[0].message.content.strip()
                print(f"[GROQ AI JSON 2025] Model: {model}, Tokens: {chat_completion.usage.total_tokens}")

                # Quick validation - ensure it looks like JSON
                if content.startswith('{') and content.endswith('}'):
                    return content
                else:
                    print(f"[GROQ AI JSON] Invalid format from {model}, trying next model")
                    continue

            except Exception as e:
                last_error = e
                print(f"[GROQ AI JSON] Model {model} failed: {type(e).__name__}: {e}")
                continue

        # All models failed
        print(f"[GROQ AI JSON ERROR] All models failed. Last error: {type(last_error).__name__}: {last_error}")
        return '{"message": "Analysis failed - all AI models unavailable", "scores": []}'

    def test_connection(self) -> bool:
        """Test if the Groq API connection is working"""
        try:
            test_response = self.ask_simple("Hello! Are you working?", max_tokens=50)
            if test_response and len(test_response) > 5:
                print("[GROQ AI] Connection test successful!")
                return True
            else:
                print("[GROQ AI] Connection test failed - empty response")
                return False
        except Exception as e:
            print(f"[GROQ AI] Connection test failed: {e}")
            return False
